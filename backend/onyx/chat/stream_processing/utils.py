from collections.abc import Sequence

from pydantic import BaseModel

from onyx.chat.models import LlmDoc
from onyx.context.search.models import InferenceChunk

from onyx.utils.logger import setup_logger

logger = setup_logger()

class DocumentIdOrderMapping(BaseModel):
    order_mapping: dict[str, int]


def map_document_id_order(
    chunks: Sequence[InferenceChunk | LlmDoc], one_indexed: bool = True
) -> DocumentIdOrderMapping:
    order_mapping = {}
    current = 1 if one_indexed else 0
    
    for chunk in chunks:
        #logger.info(f"chunk: {chunk}")
        if chunk.document_id not in order_mapping:
            # Always use sequential numbers for all documents to ensure proper citation styling
            # This includes Freshdesk custom tool data - use [1], [2], etc. instead of ticket IDs
            order_mapping[chunk.document_id] = current
            current += 1

    return DocumentIdOrderMapping(order_mapping=order_mapping)
