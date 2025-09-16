import re
from collections.abc import Generator

from onyx.chat.models import CitationInfo
from onyx.chat.models import LlmDoc
from onyx.chat.models import OnyxAnswerPiece
from onyx.chat.stream_processing.utils import DocumentIdOrderMapping
from onyx.configs.chat_configs import STOP_STREAM_PAT
from onyx.prompts.constants import TRIPLE_BACKTICK
from onyx.utils.logger import setup_logger

logger = setup_logger()


def in_code_block(llm_text: str) -> bool:
    count = llm_text.count(TRIPLE_BACKTICK)
    return count % 2 != 0


class CitationProcessor:
    def __init__(
        self,
        context_docs: list[LlmDoc],
        final_doc_id_to_rank_map: DocumentIdOrderMapping,
        display_doc_id_to_rank_map: DocumentIdOrderMapping,
        stop_stream: str | None = STOP_STREAM_PAT,
    ):
        self.context_docs = context_docs
        self.final_doc_id_to_rank_map = final_doc_id_to_rank_map
        self.display_doc_id_to_rank_map = display_doc_id_to_rank_map
        self.stop_stream = stop_stream
        self.final_order_mapping = final_doc_id_to_rank_map.order_mapping
        self.display_order_mapping = display_doc_id_to_rank_map.order_mapping
        self.llm_out = ""
        self.max_citation_num = len(context_docs)
        self.citation_order: list[int] = []  # order of citations in the LLM output
        self.curr_segment = ""
        self.cited_inds: set[int] = set()
        self.hold = ""
        self.current_citations: list[int] = []
        self.past_cite_count = 0

    def process_token(
        self, token: str | None
    ) -> Generator[OnyxAnswerPiece | CitationInfo, None, None]:
        # None -> end of stream
        if token is None:
            if self.curr_segment:
                yield OnyxAnswerPiece(answer_piece=self.curr_segment)
            return

        if self.stop_stream:
            next_hold = self.hold + token
            if self.stop_stream in next_hold:
                return
            if next_hold == self.stop_stream[: len(next_hold)]:
                self.hold = next_hold
                return
            token = next_hold
            self.hold = ""

        self.curr_segment += token
        self.llm_out += token

        # Handle code blocks without language tags
        if "`" in self.curr_segment:
            if self.curr_segment.endswith("`"):
                pass
            elif "```" in self.curr_segment:
                piece_that_comes_after = self.curr_segment.split("```")[1][0]
                if piece_that_comes_after == "\n" and in_code_block(self.llm_out):
                    self.curr_segment = self.curr_segment.replace("```", "```plaintext")

        # Handle both [1] and [[1]] formats
        citation_pattern = r"\[(\d+)\]|\[\[(\d+)\]\]"  # [1], [[1]], etc.
        citations_found = list(re.finditer(citation_pattern, self.curr_segment))
        possible_citation_pattern = r"(\[+\d*$)"  # [1, [, [[, [[2, etc.
        possible_citation_found = re.search(
            possible_citation_pattern, self.curr_segment
        )

        # Handle regular markdown links to prevent breaking them across chunks
        markdown_link_pattern = r"\[([^\]]+)\]\(([^)]+)\)"  # [text](url)
        markdown_links_found = list(re.finditer(markdown_link_pattern, self.curr_segment))
        possible_markdown_link_pattern = r"(\[[^\]]*$|\[[^\]]*\]\([^)]*$)"  # [text, [text], [text](url
        possible_markdown_link_found = re.search(
            possible_markdown_link_pattern, self.curr_segment
        )

        if len(citations_found) == 0 and len(self.llm_out) - self.past_cite_count > 5:
            self.current_citations = []

        result = ""
        
        # Don't yield incomplete segments if we have incomplete citations or markdown links
        if (possible_citation_found or possible_markdown_link_found) and not in_code_block(self.llm_out):
            return
            
        if citations_found and not in_code_block(self.curr_segment):
            last_citation_end = 0
            length_to_add = 0
            while len(citations_found) > 0:
                citation = citations_found.pop(0)
                numerical_value = int(
                    next(group for group in citation.groups() if group is not None)
                )

                logger.debug(f"Processing citation: {numerical_value}")

                if 1 <= numerical_value <= self.max_citation_num:
                    try:
                        context_llm_doc = self.context_docs[numerical_value - 1]
                        final_citation_num = self.final_order_mapping[
                            context_llm_doc.document_id
                        ]

                        if final_citation_num not in self.citation_order:
                            self.citation_order.append(final_citation_num)
                            logger.debug(f"Added citation {final_citation_num} to order")

                        citation_order_idx = (
                            self.citation_order.index(final_citation_num) + 1
                        )

                        # get the value that was displayed to user, should always
                        # be in the display_doc_order_dict. But check anyways
                        if context_llm_doc.document_id in self.display_order_mapping:
                            displayed_citation_num = self.display_order_mapping[
                                context_llm_doc.document_id
                            ]
                        else:
                            displayed_citation_num = final_citation_num
                            logger.warning(
                                f"Doc {context_llm_doc.document_id} not in display_doc_order_dict. Used LLM citation number instead."
                            )

                        # Skip consecutive citations of the same work
                        if final_citation_num in self.current_citations:
                            start, end = citation.span()
                            real_start = length_to_add + start
                            diff = end - start
                            self.curr_segment = (
                                self.curr_segment[: length_to_add + start]
                                + self.curr_segment[real_start + diff :]
                            )
                            length_to_add -= diff
                            continue

                        # Handle edge case where LLM outputs citation itself
                        if self.curr_segment.startswith("[["):
                            match = re.match(r"\[\[(\d+)\]\]", self.curr_segment)
                            if match:
                                try:
                                    doc_id = int(match.group(1))
                                    context_llm_doc = self.context_docs[doc_id - 1]
                                    citation_info = CitationInfo(
                                        citation_num=displayed_citation_num,
                                        document_id=context_llm_doc.document_id,
                                    )
                                    logger.debug(f"Yielding citation info: {citation_info}")
                                    yield citation_info
                                except Exception as e:
                                    logger.warning(
                                        f"Manual LLM citation didn't properly cite documents {e}"
                                    )
                            else:
                                logger.warning(
                                    "Manual LLM citation wasn't able to close brackets"
                                )
                            continue

                        link = context_llm_doc.link

                        self.past_cite_count = len(self.llm_out)
                        self.current_citations.append(final_citation_num)

                        if citation_order_idx not in self.cited_inds:
                            self.cited_inds.add(citation_order_idx)
                            citation_info = CitationInfo(
                                citation_num=displayed_citation_num,
                                document_id=context_llm_doc.document_id,
                            )
                            logger.debug(f"Yielding citation info: {citation_info}")
                            yield citation_info

                        start, end = citation.span()
                        if link:
                            prev_length = len(self.curr_segment)
                            # Keep the original citation format [number] instead of converting to [[number]](link)
                            # The frontend will handle the link display
                            logger.debug(f"Processing citation {numerical_value} with link: {link}")
                            self.curr_segment = (
                                self.curr_segment[: start + length_to_add]
                                + f"[[{displayed_citation_num}]]({link})"  # use the value that was displayed to user
                                + self.curr_segment[end + length_to_add :]
                            )
                            length_to_add += len(self.curr_segment) - prev_length
                            logger.debug(f"Citation {numerical_value} converted to [{displayed_citation_num}]")
                        else:
                            prev_length = len(self.curr_segment)
                            logger.debug(f"Processing citation {numerical_value} without link")
                            self.curr_segment = (
                                self.curr_segment[: start + length_to_add]
                                + f"[[{displayed_citation_num}]]()"  # use the value that was displayed to user
                                + self.curr_segment[end + length_to_add :]
                            )
                            length_to_add += len(self.curr_segment) - prev_length
                            logger.debug(f"Citation {numerical_value} converted to [{displayed_citation_num}]")

                        last_citation_end = end + length_to_add
                    except Exception as e:
                        logger.error(f"Error processing citation {numerical_value}: {e}")
                        continue

            if last_citation_end > 0:
                result += self.curr_segment[:last_citation_end]
                self.curr_segment = self.curr_segment[last_citation_end:]

        # Handle complete markdown links
        if markdown_links_found and not in_code_block(self.llm_out):
            last_link_end = 0
            for link_match in markdown_links_found:
                start, end = link_match.span()
                if start >= last_link_end:
                    result += self.curr_segment[last_link_end:end]
                    last_link_end = end
            
            if last_link_end > 0:
                self.curr_segment = self.curr_segment[last_link_end:]

        if not possible_citation_found and not possible_markdown_link_found:
            result += self.curr_segment
            self.curr_segment = ""

        if result:
            yield OnyxAnswerPiece(answer_piece=result)

import re
from collections.abc import Generator

from onyx.chat.models import LlmDoc
from onyx.chat.models import OnyxAnswerPiece
from onyx.chat.stream_processing.utils import DocumentIdOrderMapping
from onyx.configs.chat_configs import STOP_STREAM_PAT
from onyx.prompts.constants import TRIPLE_BACKTICK
from onyx.server.query_and_chat.streaming_models import CitationInfo
from onyx.utils.logger import setup_logger

logger = setup_logger()


def in_code_block(llm_text: str) -> bool:
    count = llm_text.count(TRIPLE_BACKTICK)
    return count % 2 != 0


class CitationProcessor:
    def __init__(
        self,
        context_docs: list[LlmDoc],
        final_doc_id_to_rank_map: DocumentIdOrderMapping,
        display_doc_id_to_rank_map: DocumentIdOrderMapping,
        stop_stream: str | None = STOP_STREAM_PAT,
    ):
        self.context_docs = context_docs  # list of docs in the order the LLM sees
        self.final_order_mapping = final_doc_id_to_rank_map.order_mapping
        self.display_order_mapping = display_doc_id_to_rank_map.order_mapping
        self.max_citation_num = len(context_docs)
        self.stop_stream = stop_stream

        self.llm_out = ""  # entire output so far
        self.curr_segment = ""  # tokens held for citation processing
        self.hold = ""  # tokens held for stop token processing

        self.recent_cited_documents: set[str] = set()  # docs recently cited
        self.cited_documents: set[str] = set()  # docs cited in the entire stream
        self.non_citation_count = 0

        # '[', '[[', '[1', '[[1', '[1,', '[1, ', '[1,2', '[1, 2,', etc.
        self.possible_citation_pattern = re.compile(r"(\[+(?:\d+,? ?)*$)")

        # group 1: '[[1]]', [[2]], etc.
        # group 2: '[1]', '[1, 2]', '[1,2,16]', etc.
        self.citation_pattern = re.compile(r"(\[\[\d+\]\])|(\[\d+(?:, ?\d+)*\])")

    def process_token(
        self, token: str | None
    ) -> Generator[OnyxAnswerPiece | CitationInfo, None, None]:
        # None -> end of stream
        if token is None:
            yield OnyxAnswerPiece(answer_piece=self.curr_segment)
            return

        if self.stop_stream:
            next_hold = self.hold + token
            if self.stop_stream in next_hold:
                return
            if next_hold == self.stop_stream[: len(next_hold)]:
                self.hold = next_hold
                return
            token = next_hold
            self.hold = ""

        self.curr_segment += token
        self.llm_out += token

        # Handle code blocks without language tags
        if "`" in self.curr_segment:
            if self.curr_segment.endswith("`"):
                pass
            elif "```" in self.curr_segment:
                piece_that_comes_after = self.curr_segment.split("```")[1][0]
                if piece_that_comes_after == "\n" and in_code_block(self.llm_out):
                    self.curr_segment = self.curr_segment.replace("```", "```plaintext")

        citation_matches = list(self.citation_pattern.finditer(self.curr_segment))
        possible_citation_found = bool(
            re.search(self.possible_citation_pattern, self.curr_segment)
        )

        result = ""
        if citation_matches and not in_code_block(self.llm_out):
            match_idx = 0
            for match in citation_matches:
                match_span = match.span()

                # add stuff before/between the matches
                intermatch_str = self.curr_segment[match_idx : match_span[0]]
                self.non_citation_count += len(intermatch_str)
                match_idx = match_span[1]
                result += intermatch_str

                # reset recent citations if no citations found for a while
                if self.non_citation_count > 5:
                    self.recent_cited_documents.clear()

                # process the citation string and emit citation info
                res, citation_info = self.process_citation(match)
                result += res
                for citation in citation_info:
                    yield citation
                self.non_citation_count = 0

            # leftover could be part of next citation
            self.curr_segment = self.curr_segment[match_idx:]
            self.non_citation_count = len(self.curr_segment)

        # hold onto the current segment if potential citations found, otherwise stream
        if not possible_citation_found:
            result += self.curr_segment
            self.non_citation_count += len(self.curr_segment)
            self.curr_segment = ""

        if result:
            yield OnyxAnswerPiece(answer_piece=result)

    def process_citation(self, match: re.Match) -> tuple[str, list[CitationInfo]]:
        """
        Process a single citation match and return the citation string and the
        citation info. The match string can look like '[1]', '[1, 13, 6], '[[4]]', etc.
        """
        citation_str: str = match.group()  # e.g., '[1]', '[1, 2, 3]', '[[1]]', etc.
        formatted = match.lastindex == 1  # True means already in the form '[[1]]'

        final_processed_str = ""
        final_citation_info: list[CitationInfo] = []

        # process the citation_str
        citation_content = citation_str[2:-2] if formatted else citation_str[1:-1]
        for num in (int(num) for num in citation_content.split(",")):
            # keep invalid citations as is
            if not (1 <= num <= self.max_citation_num):
                final_processed_str += f"[[{num}]]" if formatted else f"[{num}]"
                continue

            # translate the citation number of the LLM to what the user sees
            # should always be in the display_doc_order_dict. But check anyways
            context_llm_doc = self.context_docs[num - 1]
            llm_docid = context_llm_doc.document_id
            if llm_docid not in self.display_order_mapping:
                logger.warning(
                    f"Doc {llm_docid} not in display_doc_order_dict. "
                    "Used LLM citation number instead."
                )
            displayed_citation_num = self.display_order_mapping.get(
                llm_docid, self.final_order_mapping[llm_docid]
            )

            # skip citations of the same work if cited recently
            if llm_docid in self.recent_cited_documents:
                continue
            self.recent_cited_documents.add(llm_docid)

            # format the citation string
            if formatted:
                final_processed_str += citation_str
            else:
                link = context_llm_doc.link or ""
                final_processed_str += f"[[{displayed_citation_num}]]({link})"

            # create the citation info
            if llm_docid not in self.cited_documents:
                self.cited_documents.add(llm_docid)
                final_citation_info.append(
                    CitationInfo(
                        citation_num=displayed_citation_num,
                        document_id=llm_docid,
                    )
                )

        return final_processed_str, final_citation_info


class CitationProcessorGraph:
    def __init__(
        self,
        context_docs: list[LlmDoc],
        stop_stream: str | None = STOP_STREAM_PAT,
    ):
        self.context_docs = context_docs  # list of docs in the order the LLM sees
        self.max_citation_num = len(context_docs)
        self.stop_stream = stop_stream

        self.llm_out = ""  # entire output so far
        self.curr_segment = ""  # tokens held for citation processing
        self.hold = ""  # tokens held for stop token processing

        self.recent_cited_documents: set[str] = set()  # docs recently cited
        self.cited_documents: set[str] = set()  # docs cited in the entire stream
        self.non_citation_count = 0

        # '[', '[[', '[1', '[[1', '[1,', '[1, ', '[1,2', '[1, 2,', etc.
        # Also supports '[D1', '[D1, D3' type patterns
        self.possible_citation_pattern = re.compile(r"(\[+(?:(?:\d+|D\d+),? ?)*$)")

        # group 1: '[[1]]', [[2]], etc.
        # group 2: '[1]', '[1, 2]', '[1,2,16]', etc.
        # Also supports '[D1]', '[D1, D3]', '[[D1]]' type patterns
        self.citation_pattern = re.compile(
            r"(\[\[(?:\d+|D\d+)\]\])|(\[(?:\d+|D\d+)(?:, ?(?:\d+|D\d+))*\])"
        )

    def process_token(
        self, token: str | None
    ) -> str | tuple[str, list[CitationInfo]] | None:
        # None -> end of stream
        if token is None:
            return None

        if self.stop_stream:
            next_hold = self.hold + token
            if self.stop_stream in next_hold:
                return None
            if next_hold == self.stop_stream[: len(next_hold)]:
                self.hold = next_hold
                return None
            token = next_hold
            self.hold = ""

        self.curr_segment += token
        self.llm_out += token

        # Handle code blocks without language tags
        if "`" in self.curr_segment:
            if self.curr_segment.endswith("`"):
                pass
            elif "```" in self.curr_segment:
                piece_that_comes_after = self.curr_segment.split("```")[1][0]
                if piece_that_comes_after == "\n" and in_code_block(self.llm_out):
                    self.curr_segment = self.curr_segment.replace("```", "```plaintext")

        citation_matches = list(self.citation_pattern.finditer(self.curr_segment))
        possible_citation_found = bool(
            re.search(self.possible_citation_pattern, self.curr_segment)
        )

        result = ""
        if citation_matches and not in_code_block(self.llm_out):
            match_idx = 0
            citation_infos = []
            for match in citation_matches:
                match_span = match.span()

                # add stuff before/between the matches
                intermatch_str = self.curr_segment[match_idx : match_span[0]]
                self.non_citation_count += len(intermatch_str)
                match_idx = match_span[1]
                result += intermatch_str

                # reset recent citations if no citations found for a while
                if self.non_citation_count > 5:
                    self.recent_cited_documents.clear()

                # process the citation string and emit citation info
                res, citation_info = self.process_citation(match)
                result += res
                citation_infos.extend(citation_info)
                self.non_citation_count = 0

            # leftover could be part of next citation
            self.curr_segment = self.curr_segment[match_idx:]
            self.non_citation_count = len(self.curr_segment)

            return result, citation_infos

        # hold onto the current segment if potential citations found, otherwise stream
        if not possible_citation_found:
            result += self.curr_segment
            self.non_citation_count += len(self.curr_segment)
            self.curr_segment = ""

        if result:
            return result

        return None

    def process_citation(self, match: re.Match) -> tuple[str, list[CitationInfo]]:
        """
        Process a single citation match and return the citation string and the
        citation info. The match string can look like '[1]', '[1, 13, 6], '[[4]]', etc.
        """
        citation_str: str = match.group()  # e.g., '[1]', '[1, 2, 3]', '[[1]]', etc.
        formatted = match.lastindex == 1  # True means already in the form '[[1]]'

        final_processed_str = ""
        final_citation_info: list[CitationInfo] = []

        # process the citation_str
        citation_content = citation_str[2:-2] if formatted else citation_str[1:-1]
        for num in (int(num) for num in citation_content.split(",")):
            # keep invalid citations as is
            if not (1 <= num <= self.max_citation_num):
                final_processed_str += f"[[{num}]]" if formatted else f"[{num}]"
                continue

            # translate the citation number of the LLM to what the user sees
            # should always be in the display_doc_order_dict. But check anyways
            context_llm_doc = self.context_docs[num - 1]
            llm_docid = context_llm_doc.document_id

            # skip citations of the same work if cited recently
            if llm_docid in self.recent_cited_documents:
                continue
            self.recent_cited_documents.add(llm_docid)

            # format the citation string
            # if formatted:
            #     final_processed_str += f"[[{num}]]({link})"
            # else:
            link = context_llm_doc.link or ""
            final_processed_str += f"[[{num}]]({link})"

            # create the citation info
            if llm_docid not in self.cited_documents:
                self.cited_documents.add(llm_docid)
                final_citation_info.append(
                    CitationInfo(
                        citation_num=num,
                        document_id=llm_docid,
                    )
                )

        return final_processed_str, final_citation_info


class StreamExtractionProcessor:
    def __init__(self, extraction_pattern: str | None = None):
        self.extraction_pattern = extraction_pattern or "extraction_pattern"
        self.inside_extraction = False
        self.buffer = ""  # Buffer to accumulate tokens for tag detection

        # Create dynamic patterns based on extraction_pattern
        self.start_tag = f"<{self.extraction_pattern}>"
        self.end_tag = f"</{self.extraction_pattern}>"

    def process_token(self, token: str | None) -> bool | None:
        if token is None:
            # End of stream - no return value needed
            return None

        self.buffer += token

        # Check for complete start tag
        if self.start_tag in self.buffer and not self.inside_extraction:
            start_pos = self.buffer.find(self.start_tag)
            after_tag = self.buffer[start_pos + len(self.start_tag) :]

            # Set state and update buffer
            self.buffer = after_tag
            self.inside_extraction = True

            # If there's content after the tag, process it recursively
            if after_tag:
                return self.process_token("")
            return self.inside_extraction

        # Check for complete end tag
        if self.end_tag in self.buffer and self.inside_extraction:
            end_pos = self.buffer.find(self.end_tag)
            after_tag = self.buffer[end_pos + len(self.end_tag) :]

            # Set state and update buffer
            self.inside_extraction = False
            self.buffer = after_tag

            # If there's content after the tag, process it recursively
            if after_tag:
                return self.process_token("")
            return self.inside_extraction

        # Check if we might be in the middle of a tag
        if self._might_be_partial_tag(self.buffer):
            # Hold buffer, might be incomplete tag - return current state
            return self.inside_extraction

        # No complete or potential tags found, return current state
        # Clear buffer since we're processing the token
        self.buffer = ""
        return self.inside_extraction

    def _might_be_partial_tag(self, text: str) -> bool:
        """Check if text might be the start of an opening or closing extraction tag"""
        # Check for partial start tag
        for i in range(1, len(self.start_tag) + 1):
            if text.endswith(self.start_tag[:i]):
                return True

        # Check for partial end tag
        for i in range(1, len(self.end_tag) + 1):
            if text.endswith(self.end_tag[:i]):
                return True

        return False
