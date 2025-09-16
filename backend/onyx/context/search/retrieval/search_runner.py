import string
from collections.abc import Callable
from collections.abc import Iterator

import nltk  # type:ignore
from nltk.corpus import stopwords  # type:ignore
from nltk.tokenize import word_tokenize  # type:ignore
from sqlalchemy.orm import Session

from onyx.context.search.models import ChunkMetric
from onyx.context.search.models import IndexFilters
from onyx.context.search.models import InferenceChunk
from onyx.context.search.models import InferenceChunkUncleaned
from onyx.context.search.models import InferenceSection
from onyx.context.search.models import MAX_METRICS_CONTENT
from onyx.context.search.models import RetrievalMetricsContainer
from onyx.context.search.models import SearchQuery
from onyx.context.search.postprocessing.postprocessing import cleanup_chunks
from onyx.context.search.utils import inference_section_from_chunks
from onyx.db.search_settings import get_current_search_settings
from onyx.db.search_settings import get_multilingual_expansion
from onyx.document_index.interfaces import DocumentIndex
from onyx.document_index.interfaces import VespaChunkRequest
from onyx.document_index.vespa.shared_utils.utils import (
    replace_invalid_doc_id_characters,
)
from onyx.natural_language_processing.search_nlp_models import EmbeddingModel
from onyx.secondary_llm_flows.query_expansion import multilingual_query_expansion
from onyx.utils.logger import setup_logger
from onyx.utils.threadpool_concurrency import run_functions_tuples_in_parallel
from onyx.utils.timing import log_function_time
from shared_configs.configs import MODEL_SERVER_HOST
from shared_configs.configs import MODEL_SERVER_PORT
from shared_configs.enums import EmbedTextType
from onyx.configs.chat_configs import MULTILINGUAL_QUERY_EXPANSION
from onyx.db.engine import get_session_with_tenant
from onyx.db.models import SearchSettings
from onyx.context.search.enums import SearchType


logger = setup_logger()


def download_nltk_data() -> None:
    resources = {
        "stopwords": "corpora/stopwords",
        # "wordnet": "corpora/wordnet",  # Not in use
        "punkt": "tokenizers/punkt",
    }

    for resource_name, resource_path in resources.items():
        try:
            nltk.data.find(resource_path)
            logger.info(f"{resource_name} is already downloaded.")
        except LookupError:
            try:
                logger.info(f"Downloading {resource_name}...")
                nltk.download(resource_name, quiet=True)
                logger.info(f"{resource_name} downloaded successfully.")
            except Exception as e:
                logger.error(f"Failed to download {resource_name}. Error: {e}")


def lemmatize_text(keywords: list[str]) -> list[str]:
    raise NotImplementedError("Lemmatization should not be used currently")
    # try:
    #     query = " ".join(keywords)
    #     lemmatizer = WordNetLemmatizer()
    #     word_tokens = word_tokenize(query)
    #     lemmatized_words = [lemmatizer.lemmatize(word) for word in word_tokens]
    #     combined_keywords = list(set(keywords + lemmatized_words))
    #     return combined_keywords
    # except Exception:
    #     return keywords


def remove_stop_words_and_punctuation(keywords: list[str]) -> list[str]:
    try:
        # Re-tokenize using the NLTK tokenizer for better matching
        query = " ".join(keywords)
        stop_words = set(stopwords.words("english"))
        word_tokens = word_tokenize(query)
        text_trimmed = [
            word
            for word in word_tokens
            if (word.casefold() not in stop_words and word not in string.punctuation)
        ]
        return text_trimmed or word_tokens
    except Exception:
        return keywords


def combine_retrieval_results(
    chunk_sets: list[list[InferenceChunk]],
) -> list[InferenceChunk]:
    all_chunks = [chunk for chunk_set in chunk_sets for chunk in chunk_set]

    unique_chunks: dict[tuple[str, int], InferenceChunk] = {}
    for chunk in all_chunks:
        key = (chunk.document_id, chunk.chunk_id)
        if key not in unique_chunks:
            unique_chunks[key] = chunk
            continue

        stored_chunk_score = unique_chunks[key].score or 0
        this_chunk_score = chunk.score or 0
        if stored_chunk_score < this_chunk_score:
            unique_chunks[key] = chunk

    sorted_chunks = sorted(
        unique_chunks.values(), key=lambda x: x.score or 0, reverse=True
    )

    return sorted_chunks


@log_function_time(print_only=True)
def doc_index_retrieval(
    query: SearchQuery,
    document_index: DocumentIndex,
    db_session: Session,
) -> list[InferenceChunk]:
    """
    This function performs the search to retrieve the chunks,
    extracts chunks from the large chunks, persists the scores
    from the large chunks to the referenced chunks,
    dedupes the chunks, and cleans the chunks.
    """
    search_settings = get_current_search_settings(db_session)

    model = EmbeddingModel.from_db_model(
        search_settings=search_settings,
        # The below are globally set, this flow always uses the indexing one
        server_host=MODEL_SERVER_HOST,
        server_port=MODEL_SERVER_PORT,
    )

    logger.debug(f"query in doc index retrieval {query.query}")
    query_embedding = model.encode([query.query], text_type=EmbedTextType.QUERY)[0]

    top_chunks = document_index.hybrid_retrieval(
        query=query.query,
        query_embedding=query_embedding,
        final_keywords=query.processed_keywords,
        filters=query.filters,
        hybrid_alpha=query.hybrid_alpha,
        time_decay_multiplier=query.recency_bias_multiplier,
        num_to_retrieve=query.num_hits,
        offset=query.offset,
    )

    retrieval_requests: list[VespaChunkRequest] = []
    normal_chunks: list[InferenceChunkUncleaned] = []
    referenced_chunk_scores: dict[tuple[str, int], float] = {}
    for chunk in top_chunks:
        if chunk.large_chunk_reference_ids:
            retrieval_requests.append(
                VespaChunkRequest(
                    document_id=replace_invalid_doc_id_characters(chunk.document_id),
                    min_chunk_ind=chunk.large_chunk_reference_ids[0],
                    max_chunk_ind=chunk.large_chunk_reference_ids[-1],
                )
            )
            # for each referenced chunk, persist the
            # highest score to the referenced chunk
            for chunk_id in chunk.large_chunk_reference_ids:
                key = (chunk.document_id, chunk_id)
                referenced_chunk_scores[key] = max(
                    referenced_chunk_scores.get(key, 0), chunk.score or 0
                )
        else:
            normal_chunks.append(chunk)

    # If there are no large chunks, just return the normal chunks
    if not retrieval_requests:
        return cleanup_chunks(normal_chunks)

    # Retrieve and return the referenced normal chunks from the large chunks
    retrieved_inference_chunks = document_index.id_based_retrieval(
        chunk_requests=retrieval_requests,
        filters=query.filters,
        batch_retrieval=True,
    )

    # Apply the scores from the large chunks to the chunks referenced
    # by each large chunk
    for chunk in retrieved_inference_chunks:
        if (chunk.document_id, chunk.chunk_id) in referenced_chunk_scores:
            chunk.score = referenced_chunk_scores[(chunk.document_id, chunk.chunk_id)]
            referenced_chunk_scores.pop((chunk.document_id, chunk.chunk_id))
        else:
            logger.error(
                f"Chunk {chunk.document_id} {chunk.chunk_id} not found in referenced chunk scores"
            )

    # Log any chunks that were not found in the retrieved chunks
    for reference in referenced_chunk_scores.keys():
        logger.error(f"Chunk {reference} not found in retrieved chunks")

    unique_chunks: dict[tuple[str, int], InferenceChunkUncleaned] = {
        (chunk.document_id, chunk.chunk_id): chunk for chunk in normal_chunks
    }

    # persist the highest score of each deduped chunk
    for chunk in retrieved_inference_chunks:
        key = (chunk.document_id, chunk.chunk_id)
        # For duplicates, keep the highest score
        if key not in unique_chunks or (chunk.score or 0) > (
            unique_chunks[key].score or 0
        ):
            unique_chunks[key] = chunk

    # Deduplicate the chunks
    deduped_chunks = list(unique_chunks.values())
    deduped_chunks.sort(key=lambda chunk: chunk.score or 0, reverse=True)
    return cleanup_chunks(deduped_chunks)


def _simplify_text(text: str) -> str:
    return "".join(
        char for char in text if char not in string.punctuation and not char.isspace()
    ).lower()


def enhance_search_results_with_source_pages(
    chunks: list[InferenceChunk],
    document_index: DocumentIndex,
    query: SearchQuery,
    db_session: Session,
) -> list[InferenceChunk]:
    """
    Enhance search results by including source documents when image documents are found.
    This works universally across all connectors by using document ID relationships
    stored in image metadata.
    """
    if not chunks:
        return chunks

    # Find image documents and their source document IDs
    image_chunks = []
    source_document_ids = set()

    for chunk in chunks:
        # Check if this is an image document by looking at metadata
        if chunk.metadata:
            source_doc_id = chunk.metadata.get("source_document_id")
            # Check if this is an image document (has source_document_id and is from image processing)
            if source_doc_id and chunk.metadata.get("source") in ["web_embedded", "web_embedded_cdn", "web_embedded_fallback", "file_embedded", "drive_embedded"]:
                image_chunks.append(chunk)
                source_document_ids.add(source_doc_id)
                logger.debug(f"Found image document with source document ID: {source_doc_id}")

    if not image_chunks or not source_document_ids:
        # No image documents found, return original results
        return chunks

    logger.info(f"Found {len(image_chunks)} image documents from {len(source_document_ids)} source documents. Fetching source documents.")

    # Search for the source documents using document IDs
    source_document_chunks = []
    for source_doc_id in source_document_ids:
        try:
            # Create a new SearchQuery instance for the source document search
            source_query = SearchQuery(
                query=f'document_id:"{source_doc_id}"',  # Search by document ID
                processed_keywords=query.processed_keywords,
                search_type=query.search_type,
                evaluation_type=query.evaluation_type,
                filters=query.filters,
                chunks_above=query.chunks_above,
                chunks_below=query.chunks_below,
                rerank_settings=query.rerank_settings,
                hybrid_alpha=query.hybrid_alpha,
                recency_bias_multiplier=query.recency_bias_multiplier,
                max_llm_filter_sections=query.max_llm_filter_sections,
                num_hits=5,  # Get a few chunks from the source document
                offset=0,  # Reset offset
                full_doc=query.full_doc
            )

            # Perform the search for source document
            doc_chunks = doc_index_retrieval(
                query=source_query,
                document_index=document_index,
                db_session=db_session,
            )

            # Filter to only include chunks from the exact source document
            for chunk in doc_chunks:
                if chunk.document_id == source_doc_id:
                    # Boost the score to ensure source documents appear prominently
                    if chunk.score:
                        chunk.score = chunk.score * 1.8  # 80% boost for source documents
                    else:
                        chunk.score = 0.9  # Give a good score even if originally 0
                    
                    source_document_chunks.append(chunk)
                    logger.debug(f"Added source document chunk: {source_doc_id} with boosted score: {chunk.score}")

        except Exception as e:
            logger.warning(f"Failed to retrieve source document for {source_doc_id}: {e}")
            continue

    if not source_document_chunks:
        logger.debug("No source document chunks found, returning original results")
        return chunks

    # Combine results with proper prioritization
    enhanced_chunks = []
    
    # Add source document chunks (highest priority)
    enhanced_chunks.extend(source_document_chunks)
    
    # Add image documents (medium priority) 
    for image_chunk in image_chunks:
        # Boost image scores so they appear after source docs but before other content
        if image_chunk.score:
            image_chunk.score = image_chunk.score * 1.3  # 30% boost
        enhanced_chunks.append(image_chunk)
    
    # Add other non-image documents (original priority)
    existing_doc_ids = {chunk.document_id for chunk in enhanced_chunks}
    for chunk in chunks:
        if chunk.document_id not in existing_doc_ids:
            enhanced_chunks.append(chunk)

    # Re-sort by score to maintain relevance order
    enhanced_chunks.sort(key=lambda x: x.score or 0, reverse=True)

    # Limit results but ensure we include source documents and images
    min_results = len(source_document_chunks) + len(image_chunks)
    max_results = max(query.num_hits, min_results)
    final_chunks = enhanced_chunks[:max_results]

    logger.info(f"Enhanced search results: {len(source_document_chunks)} source document chunks + {len(image_chunks)} images + {len(final_chunks) - len(source_document_chunks) - len(image_chunks)} other = {len(final_chunks)} total")

    return final_chunks


def retrieve_chunks(
    query: SearchQuery,
    document_index: DocumentIndex,
    db_session: Session,
    retrieval_metrics_callback: Callable[[RetrievalMetricsContainer], None]
    | None = None,
) -> list[InferenceChunk]:
    """Returns a list of the best chunks from an initial keyword/semantic/ hybrid search."""

    multilingual_expansion = get_multilingual_expansion(db_session)
    # Don't do query expansion on complex queries, rephrasings likely would not work well
    if not multilingual_expansion or "\n" in query.query or "\r" in query.query:
        top_chunks = doc_index_retrieval(
            query=query, document_index=document_index, db_session=db_session
        )
    else:
        simplified_queries = set()
        run_queries: list[tuple[Callable, tuple]] = []

        # Currently only uses query expansion on multilingual use cases
        query_rephrases = multilingual_query_expansion(
            query.query, multilingual_expansion
        )
        # Just to be extra sure, add the original query.
        query_rephrases.append(query.query)
        for rephrase in set(query_rephrases):
            # Sometimes the model rephrases the query in the same language with minor changes
            # Avoid doing an extra search with the minor changes as this biases the results
            simplified_rephrase = _simplify_text(rephrase)
            if simplified_rephrase in simplified_queries:
                continue
            simplified_queries.add(simplified_rephrase)

            q_copy = query.copy(update={"query": rephrase}, deep=True)
            run_queries.append(
                (
                    doc_index_retrieval,
                    (q_copy, document_index, db_session),
                )
            )
        parallel_search_results = run_functions_tuples_in_parallel(run_queries)
        top_chunks = combine_retrieval_results(parallel_search_results)

    if not top_chunks:
        logger.warning(
            f"Hybrid ({query.search_type.value.capitalize()}) search returned no results "
            f"with filters: {query.filters}"
        )
        return []

    # Enhance search results with source page documents when image documents are found
    top_chunks = enhance_search_results_with_source_pages(
        chunks=top_chunks,
        document_index=document_index,
        query=query,
        db_session=db_session,
    )

    if retrieval_metrics_callback is not None:
        chunk_metrics = [
            ChunkMetric(
                document_id=chunk.document_id,
                chunk_content_start=chunk.content[:MAX_METRICS_CONTENT],
                first_link=chunk.source_links[0] if chunk.source_links else None,
                score=chunk.score if chunk.score is not None else 0,
            )
            for chunk in top_chunks
        ]
        retrieval_metrics_callback(
            RetrievalMetricsContainer(
                search_type=query.search_type, metrics=chunk_metrics
            )
        )

    return top_chunks


def inference_sections_from_ids(
    doc_identifiers: list[tuple[str, int]],
    document_index: DocumentIndex,
) -> list[InferenceSection]:
    # Currently only fetches whole docs
    doc_ids_set = set(doc_id for doc_id, _ in doc_identifiers)

    chunk_requests: list[VespaChunkRequest] = [
        VespaChunkRequest(document_id=doc_id) for doc_id in doc_ids_set
    ]

    # No need for ACL here because the doc ids were validated beforehand
    filters = IndexFilters(access_control_list=None)

    retrieved_chunks = document_index.id_based_retrieval(
        chunk_requests=chunk_requests,
        filters=filters,
    )

    cleaned_chunks = cleanup_chunks(retrieved_chunks)
    if not cleaned_chunks:
        return []

    # Group chunks by document ID
    chunks_by_doc_id: dict[str, list[InferenceChunk]] = {}
    for chunk in cleaned_chunks:
        chunks_by_doc_id.setdefault(chunk.document_id, []).append(chunk)

    inference_sections = [
        section
        for chunks in chunks_by_doc_id.values()
        if chunks
        and (
            section := inference_section_from_chunks(
                # The scores will always be 0 because the fetching by id gives back
                # no search scores. This is not needed though if the user is explicitly
                # selecting a document.
                center_chunk=chunks[0],
                chunks=chunks,
            )
        )
    ]

    return inference_sections

import string
from collections.abc import Callable
from uuid import UUID

import nltk  # type:ignore
from sqlalchemy.orm import Session

from onyx.agents.agent_search.shared_graph_utils.models import QueryExpansionType
from onyx.context.search.enums import SearchType
from onyx.context.search.models import ChunkMetric
from onyx.context.search.models import IndexFilters
from onyx.context.search.models import InferenceChunk
from onyx.context.search.models import InferenceChunkUncleaned
from onyx.context.search.models import InferenceSection
from onyx.context.search.models import MAX_METRICS_CONTENT
from onyx.context.search.models import RetrievalMetricsContainer
from onyx.context.search.models import SearchQuery
from onyx.context.search.postprocessing.postprocessing import cleanup_chunks
from onyx.context.search.preprocessing.preprocessing import HYBRID_ALPHA
from onyx.context.search.preprocessing.preprocessing import HYBRID_ALPHA_KEYWORD
from onyx.context.search.utils import get_query_embedding
from onyx.context.search.utils import get_query_embeddings
from onyx.context.search.utils import inference_section_from_chunks
from onyx.db.search_settings import get_multilingual_expansion
from onyx.document_index.interfaces import DocumentIndex
from onyx.document_index.interfaces import VespaChunkRequest
from onyx.document_index.vespa.shared_utils.utils import (
    replace_invalid_doc_id_characters,
)
from onyx.federated_connectors.federated_retrieval import (
    get_federated_retrieval_functions,
)
from onyx.secondary_llm_flows.query_expansion import multilingual_query_expansion
from onyx.utils.logger import setup_logger
from onyx.utils.threadpool_concurrency import run_functions_tuples_in_parallel
from onyx.utils.threadpool_concurrency import run_in_background
from onyx.utils.threadpool_concurrency import TimeoutThread
from onyx.utils.threadpool_concurrency import wait_on_background
from onyx.utils.timing import log_function_time
from shared_configs.model_server_models import Embedding

logger = setup_logger()


def _dedupe_chunks(
    chunks: list[InferenceChunkUncleaned],
) -> list[InferenceChunkUncleaned]:
    used_chunks: dict[tuple[str, int], InferenceChunkUncleaned] = {}
    for chunk in chunks:
        key = (chunk.document_id, chunk.chunk_id)
        if key not in used_chunks:
            used_chunks[key] = chunk
        else:
            stored_chunk_score = used_chunks[key].score or 0
            this_chunk_score = chunk.score or 0
            if stored_chunk_score < this_chunk_score:
                used_chunks[key] = chunk

    return list(used_chunks.values())


def download_nltk_data() -> None:
    resources = {
        "stopwords": "corpora/stopwords",
        # "wordnet": "corpora/wordnet",  # Not in use
        "punkt_tab": "tokenizers/punkt_tab",
    }

    for resource_name, resource_path in resources.items():
        try:
            nltk.data.find(resource_path)
            logger.info(f"{resource_name} is already downloaded.")
        except LookupError:
            try:
                logger.info(f"Downloading {resource_name}...")
                nltk.download(resource_name, quiet=True)
                logger.info(f"{resource_name} downloaded successfully.")
            except Exception as e:
                logger.error(f"Failed to download {resource_name}. Error: {e}")


def lemmatize_text(keywords: list[str]) -> list[str]:
    raise NotImplementedError("Lemmatization should not be used currently")
    # try:
    #     query = " ".join(keywords)
    #     lemmatizer = WordNetLemmatizer()
    #     word_tokens = word_tokenize(query)
    #     lemmatized_words = [lemmatizer.lemmatize(word) for word in word_tokens]
    #     combined_keywords = list(set(keywords + lemmatized_words))
    #     return combined_keywords
    # except Exception:
    #     return keywords


def combine_retrieval_results(
    chunk_sets: list[list[InferenceChunk]],
) -> list[InferenceChunk]:
    all_chunks = [chunk for chunk_set in chunk_sets for chunk in chunk_set]

    unique_chunks: dict[tuple[str, int], InferenceChunk] = {}
    for chunk in all_chunks:
        key = (chunk.document_id, chunk.chunk_id)
        if key not in unique_chunks:
            unique_chunks[key] = chunk
            continue

        stored_chunk_score = unique_chunks[key].score or 0
        this_chunk_score = chunk.score or 0
        if stored_chunk_score < this_chunk_score:
            unique_chunks[key] = chunk

    sorted_chunks = sorted(
        unique_chunks.values(), key=lambda x: x.score or 0, reverse=True
    )

    return sorted_chunks


@log_function_time(print_only=True)
def doc_index_retrieval(
    query: SearchQuery,
    document_index: DocumentIndex,
    db_session: Session,
) -> list[InferenceChunk]:
    """
    This function performs the search to retrieve the chunks,
    extracts chunks from the large chunks, persists the scores
    from the large chunks to the referenced chunks,
    dedupes the chunks, and cleans the chunks.
    """
    query_embedding = query.precomputed_query_embedding or get_query_embedding(
        query.query, db_session
    )

    keyword_embeddings_thread: TimeoutThread[list[Embedding]] | None = None
    semantic_embeddings_thread: TimeoutThread[list[Embedding]] | None = None
    top_base_chunks_standard_ranking_thread: (
        TimeoutThread[list[InferenceChunkUncleaned]] | None
    ) = None

    top_semantic_chunks_thread: TimeoutThread[list[InferenceChunkUncleaned]] | None = (
        None
    )

    keyword_embeddings: list[Embedding] | None = None
    semantic_embeddings: list[Embedding] | None = None

    top_semantic_chunks: list[InferenceChunkUncleaned] | None = None

    # original retrieveal method
    top_base_chunks_standard_ranking_thread = run_in_background(
        document_index.hybrid_retrieval,
        query.query,
        query_embedding,
        query.processed_keywords,
        query.filters,
        query.hybrid_alpha,
        query.recency_bias_multiplier,
        query.num_hits,
        QueryExpansionType.SEMANTIC,
        query.offset,
    )

    if (
        query.expanded_queries
        and query.expanded_queries.keywords_expansions
        and query.expanded_queries.semantic_expansions
    ):

        keyword_embeddings_thread = run_in_background(
            get_query_embeddings,
            query.expanded_queries.keywords_expansions,
            db_session,
        )

        if query.search_type == SearchType.SEMANTIC:
            semantic_embeddings_thread = run_in_background(
                get_query_embeddings,
                query.expanded_queries.semantic_expansions,
                db_session,
            )

        keyword_embeddings = wait_on_background(keyword_embeddings_thread)
        if query.search_type == SearchType.SEMANTIC:
            assert semantic_embeddings_thread is not None
            semantic_embeddings = wait_on_background(semantic_embeddings_thread)

        # Use original query embedding for keyword retrieval embedding
        keyword_embeddings = [query_embedding]

        # Note: we generally prepped earlier for multiple expansions, but for now we only use one.
        top_keyword_chunks_thread = run_in_background(
            document_index.hybrid_retrieval,
            query.expanded_queries.keywords_expansions[0],
            keyword_embeddings[0],
            query.processed_keywords,
            query.filters,
            HYBRID_ALPHA_KEYWORD,
            query.recency_bias_multiplier,
            query.num_hits,
            QueryExpansionType.KEYWORD,
            query.offset,
        )

        if query.search_type == SearchType.SEMANTIC:
            assert semantic_embeddings is not None

            top_semantic_chunks_thread = run_in_background(
                document_index.hybrid_retrieval,
                query.expanded_queries.semantic_expansions[0],
                semantic_embeddings[0],
                query.processed_keywords,
                query.filters,
                HYBRID_ALPHA,
                query.recency_bias_multiplier,
                query.num_hits,
                QueryExpansionType.SEMANTIC,
                query.offset,
            )

        top_base_chunks_standard_ranking = wait_on_background(
            top_base_chunks_standard_ranking_thread
        )

        top_keyword_chunks = wait_on_background(top_keyword_chunks_thread)

        if query.search_type == SearchType.SEMANTIC:
            assert top_semantic_chunks_thread is not None
            top_semantic_chunks = wait_on_background(top_semantic_chunks_thread)

        all_top_chunks = top_base_chunks_standard_ranking + top_keyword_chunks

        # use all three retrieval methods to retrieve top chunks

        if query.search_type == SearchType.SEMANTIC and top_semantic_chunks is not None:

            all_top_chunks += top_semantic_chunks

        top_chunks = _dedupe_chunks(all_top_chunks)

    else:

        top_base_chunks_standard_ranking = wait_on_background(
            top_base_chunks_standard_ranking_thread
        )

        top_chunks = _dedupe_chunks(top_base_chunks_standard_ranking)

    logger.info(f"Overall number of top initial retrieval chunks: {len(top_chunks)}")

    retrieval_requests: list[VespaChunkRequest] = []
    normal_chunks: list[InferenceChunkUncleaned] = []
    referenced_chunk_scores: dict[tuple[str, int], float] = {}
    for chunk in top_chunks:
        if chunk.large_chunk_reference_ids:
            retrieval_requests.append(
                VespaChunkRequest(
                    document_id=replace_invalid_doc_id_characters(chunk.document_id),
                    min_chunk_ind=chunk.large_chunk_reference_ids[0],
                    max_chunk_ind=chunk.large_chunk_reference_ids[-1],
                )
            )
            # for each referenced chunk, persist the
            # highest score to the referenced chunk
            for chunk_id in chunk.large_chunk_reference_ids:
                key = (chunk.document_id, chunk_id)
                referenced_chunk_scores[key] = max(
                    referenced_chunk_scores.get(key, 0), chunk.score or 0
                )
        else:
            normal_chunks.append(chunk)

    # If there are no large chunks, just return the normal chunks
    if not retrieval_requests:
        return cleanup_chunks(normal_chunks)

    # Retrieve and return the referenced normal chunks from the large chunks
    retrieved_inference_chunks = document_index.id_based_retrieval(
        chunk_requests=retrieval_requests,
        filters=query.filters,
        batch_retrieval=True,
    )

    # Apply the scores from the large chunks to the chunks referenced
    # by each large chunk
    for chunk in retrieved_inference_chunks:
        if (chunk.document_id, chunk.chunk_id) in referenced_chunk_scores:
            chunk.score = referenced_chunk_scores[(chunk.document_id, chunk.chunk_id)]
            referenced_chunk_scores.pop((chunk.document_id, chunk.chunk_id))
        else:
            logger.error(
                f"Chunk {chunk.document_id} {chunk.chunk_id} not found in referenced chunk scores"
            )

    # Log any chunks that were not found in the retrieved chunks
    for reference in referenced_chunk_scores.keys():
        logger.error(f"Chunk {reference} not found in retrieved chunks")

    unique_chunks: dict[tuple[str, int], InferenceChunkUncleaned] = {
        (chunk.document_id, chunk.chunk_id): chunk for chunk in normal_chunks
    }

    # persist the highest score of each deduped chunk
    for chunk in retrieved_inference_chunks:
        key = (chunk.document_id, chunk.chunk_id)
        # For duplicates, keep the highest score
        if key not in unique_chunks or (chunk.score or 0) > (
            unique_chunks[key].score or 0
        ):
            unique_chunks[key] = chunk

    # Deduplicate the chunks
    deduped_chunks = list(unique_chunks.values())
    deduped_chunks.sort(key=lambda chunk: chunk.score or 0, reverse=True)
    return cleanup_chunks(deduped_chunks)


def _simplify_text(text: str) -> str:
    return "".join(
        char for char in text if char not in string.punctuation and not char.isspace()
    ).lower()


def retrieve_chunks(
    query: SearchQuery,
    user_id: UUID | None,
    document_index: DocumentIndex,
    db_session: Session,
    retrieval_metrics_callback: (
        Callable[[RetrievalMetricsContainer], None] | None
    ) = None,
) -> list[InferenceChunk]:
    """Returns a list of the best chunks from an initial keyword/semantic/ hybrid search."""

    multilingual_expansion = get_multilingual_expansion(db_session)
    run_queries: list[tuple[Callable, tuple]] = []

    source_filters = (
        set(query.filters.source_type) if query.filters.source_type else None
    )

    # Federated retrieval
    federated_retrieval_infos = get_federated_retrieval_functions(
        db_session, user_id, query.filters.source_type, query.filters.document_set
    )
    federated_sources = set(
        federated_retrieval_info.source.to_non_federated_source()
        for federated_retrieval_info in federated_retrieval_infos
    )
    for federated_retrieval_info in federated_retrieval_infos:
        run_queries.append((federated_retrieval_info.retrieval_function, (query,)))

    # Normal retrieval
    normal_search_enabled = (source_filters is None) or (
        len(set(source_filters) - federated_sources) > 0
    )
    if normal_search_enabled and (
        not multilingual_expansion or "\n" in query.query or "\r" in query.query
    ):
        # Don't do query expansion on complex queries, rephrasings likely would not work well
        run_queries.append((doc_index_retrieval, (query, document_index, db_session)))
    elif normal_search_enabled:
        simplified_queries = set()

        # Currently only uses query expansion on multilingual use cases
        query_rephrases = multilingual_query_expansion(
            query.query, multilingual_expansion
        )
        # Just to be extra sure, add the original query.
        query_rephrases.append(query.query)
        for rephrase in set(query_rephrases):
            # Sometimes the model rephrases the query in the same language with minor changes
            # Avoid doing an extra search with the minor changes as this biases the results
            simplified_rephrase = _simplify_text(rephrase)
            if simplified_rephrase in simplified_queries:
                continue
            simplified_queries.add(simplified_rephrase)

            q_copy = query.model_copy(
                update={
                    "query": rephrase,
                    # need to recompute for each rephrase
                    # note that `SearchQuery` is a frozen model, so we can't update
                    # it below
                    "precomputed_query_embedding": None,
                },
                deep=True,
            )
            run_queries.append(
                (doc_index_retrieval, (q_copy, document_index, db_session))
            )

    parallel_search_results = run_functions_tuples_in_parallel(run_queries)
    top_chunks = combine_retrieval_results(parallel_search_results)

    if not top_chunks:
        logger.warning(
            f"Hybrid ({query.search_type.value.capitalize()}) search returned no results "
            f"with filters: {query.filters}"
        )
        return []

    if retrieval_metrics_callback is not None:
        chunk_metrics = [
            ChunkMetric(
                document_id=chunk.document_id,
                chunk_content_start=chunk.content[:MAX_METRICS_CONTENT],
                first_link=chunk.source_links[0] if chunk.source_links else None,
                score=chunk.score if chunk.score is not None else 0,
            )
            for chunk in top_chunks
        ]
        retrieval_metrics_callback(
            RetrievalMetricsContainer(
                search_type=query.search_type, metrics=chunk_metrics
            )
        )

    return top_chunks


def inference_sections_from_ids(
    doc_identifiers: list[tuple[str, int]],
    document_index: DocumentIndex,
) -> list[InferenceSection]:
    # Currently only fetches whole docs
    doc_ids_set = set(doc_id for doc_id, _ in doc_identifiers)

    chunk_requests: list[VespaChunkRequest] = [
        VespaChunkRequest(document_id=doc_id) for doc_id in doc_ids_set
    ]

    # No need for ACL here because the doc ids were validated beforehand
    filters = IndexFilters(access_control_list=None)

    retrieved_chunks = document_index.id_based_retrieval(
        chunk_requests=chunk_requests,
        filters=filters,
    )

    cleaned_chunks = cleanup_chunks(retrieved_chunks)
    if not cleaned_chunks:
        return []

    # Group chunks by document ID
    chunks_by_doc_id: dict[str, list[InferenceChunk]] = {}
    for chunk in cleaned_chunks:
        chunks_by_doc_id.setdefault(chunk.document_id, []).append(chunk)

    inference_sections = [
        section
        for chunks in chunks_by_doc_id.values()
        if chunks
        and (
            section := inference_section_from_chunks(
                # The scores will always be 0 because the fetching by id gives back
                # no search scores. This is not needed though if the user is explicitly
                # selecting a document.
                center_chunk=chunks[0],
                chunks=chunks,
            )
        )
    ]

    return inference_sections
