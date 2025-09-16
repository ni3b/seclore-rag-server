from collections.abc import Callable
import re
import time
from typing import Callable
from typing import cast
from onyx.natural_language_processing.utils import get_tokenizer
from onyx.utils.timing import log_function_time
from onyx.configs.app_configs import LLM_API_CONCURRENCY_LIMIT
from onyx.configs.chat_configs import DISABLE_LLM_DOC_RELEVANCE
from onyx.llm.interfaces import LLM, LLMConfig
from onyx.llm.utils import check_number_of_tokens, dict_based_prompt_to_langchain_prompt
from onyx.llm.utils import message_to_string
from onyx.prompts.llm_chunk_filter import NONUSEFUL_PAT
from onyx.prompts.llm_chunk_filter import SECTION_FILTER_PROMPT
from onyx.utils.logger import setup_logger
from onyx.utils.threadpool_concurrency import run_functions_tuples_in_parallel_with_rate_limiting
from onyx.llm.interfaces import LLMConfig

logger = setup_logger()


def llm_eval_section(
    query: str,
    section_content: str,
    llm: LLM,
    title: str,
    metadata: dict[str, str | list[str]],
) -> bool:
    """
    Evaluate one section in a single LLM call.
    """
    def _get_metadata_str(metadata: dict[str, str | list[str]]) -> str:
        metadata_str = "\nMetadata:\n"
        for key, value in metadata.items():
            value_str = ", ".join(value) if isinstance(value, list) else value
            metadata_str += f"{key} - {value_str}\n"
        return metadata_str

    def _get_usefulness_messages() -> list[dict[str, str]]:
        metadata_str = _get_metadata_str(metadata) if metadata else ""
        messages = [
            {
                "role": "user",
                "content": SECTION_FILTER_PROMPT.format(
                    title=title.replace("\n", " "),
                    chunk_text=section_content,
                    user_query=query,
                    optional_metadata=metadata_str,
                ),
            },
        ]
        return messages

    def _extract_usefulness(model_output: str) -> bool:
        """Default useful if the LLM doesn't match pattern exactly
        This is because it's better to trust the (re)ranking if LLM fails"""
        if model_output.strip().strip('"').lower() == NONUSEFUL_PAT.lower():
            return False
        return True

    messages = _get_usefulness_messages()
    filled_llm_prompt = dict_based_prompt_to_langchain_prompt(messages)
    model_output = message_to_string(llm.invoke(filled_llm_prompt))
    #logger.debug(model_output)

    return _extract_usefulness(model_output)


def llm_eval_sections_single_batch(
    query: str,
    section_contents: list[str],
    llm: LLM,
    titles: list[str],
    metadata_list: list[dict[str, str | list[str]]],
) -> list[bool]:
    """
    Evaluate a batch of sections in a single LLM call.
    Returns a list of booleans indicating relevance per section.
    """
    start_time = time.time()

    # Build combined prompt
    batch_prompt_lines = [
        f"Query: \"{query}\"",
        "For each section below, reply ONLY with 'Yes' if relevant to the query or 'No' if not relevant.",
        "Format your output as: <section_number>: Yes/No",
        "",
    ]

    for idx, (content, title, metadata) in enumerate(zip(section_contents, titles, metadata_list), start=1):
        metadata_str = ""
        if metadata:
            metadata_str = "\nMetadata:\n" + "\n".join(
                f"{k} - {', '.join(v) if isinstance(v, list) else v}" for k, v in metadata.items()
            )

        clean_title = title.replace("\n", " ")
        batch_prompt_lines.append(
            f"{idx}. Title: {clean_title}{metadata_str}Content: {content}"
        )


    full_prompt = "\n".join(batch_prompt_lines)

    token_start_time = time.time()
    token_count = check_tokens_of_batched_prompt(full_prompt, llm.config) 
    token_end_time = time.time()

    messages = [{"role": "user", "content": full_prompt}]
    filled_llm_prompt = dict_based_prompt_to_langchain_prompt(messages)
    model_output = message_to_string(llm.invoke(filled_llm_prompt))
    output_end_time = time.time()

    # Parse LLM output
    results = []
    for idx in range(1, len(section_contents) + 1):
        line_match = re.search(rf"{idx}\s*[:\-]\s*(yes|no)", model_output, re.IGNORECASE)
        results.append(line_match.group(1).strip().lower() == "yes" if line_match else True)

    logger.info(f"Token count for batch took: {token_end_time - token_start_time:.2f}s")
    logger.info(f"LLM call for batch took: {output_end_time - token_end_time:.2f}s")
    logger.info(f"Final token count for batch : {token_count}") 
    logger.info(f"Batch evaluation completed in {time.time() - start_time:.2f}s for {len(section_contents)} sections")
    return results


# -------------------------------------------------------------------
# Main function: Supports four modes
# -------------------------------------------------------------------
@log_function_time(print_only=True)
def llm_batch_eval_sections(
    query: str,
    section_contents: list[str],
    llm: LLM,
    titles: list[str],
    metadata_list: list[dict[str, str | list[str]]],
    use_threads: bool = True, # Important to enable this for parallelization
    use_single_batch: bool = False,
    batch_size: int = 25  # If set, will process in chunks of this size
) -> list[bool]:
    """
    Evaluate section relevance using one of four modes:
    1. Threaded & custom batch size (use_threads=True, use_single_batch=False, batch_size set to an integer), fallback: sequential execution of batches
    2. Single batch of all sections (use_threads=False, use_single_batch=True, batch_size=None)
    3. Threaded per-section calls (original, use_threads=True, use_single_batch=False, batch_size=None)
    4. Fallback: Sequential execution of per-section calls
    """

    if DISABLE_LLM_DOC_RELEVANCE:
        raise RuntimeError("LLM Doc Relevance is globally disabled.")

    # -------------------------------------------------
    # Mode 2: Single-batch evaluation (all sections at once)
    # -------------------------------------------------
    if use_single_batch and not batch_size:
        logger.info(f"Running SINGLE-BATCH evaluation for {len(section_contents)} sections")
        return llm_eval_sections_single_batch(query, section_contents, llm, titles, metadata_list)


    # -------------------------------------------------
    # Mode 3: Custom batch size
    # -------------------------------------------------

    if batch_size and batch_size > 0:
        logger.info(f"Running BATCH-SIZE evaluation: {batch_size} per batch, total {len(section_contents)} sections")
        start_time = time.time()

        # Build batches
        batch_args = []
        for start_idx in range(0, len(section_contents), batch_size):
            end_idx = min(start_idx + batch_size, len(section_contents))
            batch_sections = section_contents[start_idx:end_idx]
            batch_titles = titles[start_idx:end_idx]
            batch_metadata = metadata_list[start_idx:end_idx]

            batch_args.append((query, batch_sections, llm, batch_titles, batch_metadata))

        # Option A: Parallelize batch calls
        if use_threads:
            logger.info(f"Processing {len(batch_args)} batches in parallel with threads")

            functions_with_args = [
                (llm_eval_sections_single_batch, args) for args in batch_args
            ]

            parallel_results = run_functions_tuples_in_parallel_with_rate_limiting(
                functions_with_args,
                allow_failures=True,
                max_workers=LLM_API_CONCURRENCY_LIMIT,
                use_rate_limiting=True,
                use_retry=True
            )

            # Flatten results from all batches
            all_results = []
            for batch_result in parallel_results:
                if batch_result is None:
                    logger.warning("A batch failed, marking all its items as False")
                    all_results.extend([False] * batch_size)
                else:
                    all_results.extend(batch_result)

        # Option B: Sequential batches
        else:
            logger.info("Processing batches sequentially")
            all_results = []
            for idx, args in enumerate(batch_args, start=1):
                logger.debug(f"Processing batch {idx}/{len(batch_args)}")
                batch_result = llm_eval_sections_single_batch(*args)
                all_results.extend(batch_result)

        logger.info(f"Batch-size evaluation completed in {time.time() - start_time:.2f}s")
        return all_results

    # -------------------------------------------------
    # Mode 1: Traditional threaded per-section calls
    # -------------------------------------------------
    if use_threads:
        logger.info(f"Running THREADED evaluation for {len(section_contents)} sections")
        start_time = time.time()

        functions_with_args: list[tuple[Callable, tuple]] = [
            (llm_eval_section, (query, section_content, llm, title, metadata))
            for section_content, title, metadata in zip(section_contents, titles, metadata_list)
        ]

        parallel_results = run_functions_tuples_in_parallel_with_rate_limiting(
            functions_with_args,
            allow_failures=True,
            max_workers=LLM_API_CONCURRENCY_LIMIT,
            use_rate_limiting=True,
            use_retry=True
        )

        failed_count = sum(1 for item in parallel_results if item is None)
        if failed_count > 0:
            logger.warning(f"{failed_count}/{len(parallel_results)} threaded calls failed. Marking them as False.")

        logger.info(f"Threaded evaluation completed in {time.time() - start_time:.2f}s")
        results = [False if item is None else item for item in parallel_results]

        return results


    # -------------------------------------------------
    # Mode 4 (Sequential fallback)
    # -------------------------------------------------
    logger.info(f"Running SEQUENTIAL evaluation for {len(section_contents)} sections")
    start_time = time.time()
    results = [
        llm_eval_section(query, section_content, llm, title, metadata)
        for section_content, title, metadata in zip(section_contents, titles, metadata_list)
    ]
    logger.info(f"Sequential evaluation completed in {time.time() - start_time:.2f}s")
    return results


def check_tokens_of_batched_prompt(prompt: str, llm_config: LLMConfig) -> int:
    llm_tokenizer = get_tokenizer(
        provider_type=llm_config.model_provider,
        model_name=llm_config.model_name,
    )
    llm_tokenizer_encode_func = cast(Callable[[str], list[int]], llm_tokenizer.encode)

    return check_number_of_tokens(prompt, llm_tokenizer_encode_func)