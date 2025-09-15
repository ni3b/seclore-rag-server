import time
import uuid
from collections.abc import Callable
from concurrent.futures import as_completed
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from typing import Generic
from typing import TypeVar
import threading
import random

from litellm.exceptions import RateLimitError  # type: ignore

from onyx.configs.app_configs import LLM_API_CONCURRENCY_LIMIT
from onyx.utils.logger import setup_logger

logger = setup_logger()

R = TypeVar("R")

# Global semaphore to limit concurrent LLM API calls
_LLM_API_SEMAPHORE = threading.Semaphore(LLM_API_CONCURRENCY_LIMIT)
_SEMAPHORE_LOCK = threading.Lock()


def set_llm_concurrency_limit(limit: int) -> None:
    """Set the maximum number of concurrent LLM API calls allowed."""
    global _LLM_API_SEMAPHORE
    with _SEMAPHORE_LOCK:
        _LLM_API_SEMAPHORE = threading.Semaphore(limit)


def retry_with_exponential_backoff(
    func: Callable,
    args: tuple,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    jitter: bool = True,
) -> Any:
    """
    Execute a function with exponential backoff retry on rate limit errors.
    
    Args:
        func: Function to execute
        args: Arguments to pass to the function
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Factor to multiply delay by each retry
        jitter: Whether to add random jitter to delay
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return func(*args)
        except RateLimitError as e:
            last_exception = e
            if attempt >= max_retries:
                logger.error(f"Max retries ({max_retries}) exceeded for rate limit error: {e}")
                break
                
            # Calculate delay with exponential backoff
            delay = min(base_delay * (backoff_factor ** attempt), max_delay)
            
            # Add jitter to prevent thundering herd
            if jitter:
                delay *= (0.5 + random.random() * 0.5)
            
            logger.warning(f"Rate limit hit, retrying in {delay:.2f}s (attempt {attempt + 1}/{max_retries + 1}): {e}")
            time.sleep(delay)
        except Exception as e:
            # For non-rate-limit errors, don't retry
            raise e
    
    # If we get here, all retries failed
    raise last_exception


def run_functions_tuples_in_parallel_with_rate_limiting(
    functions_with_args: list[tuple[Callable, tuple]],
    allow_failures: bool = False,
    max_workers: int | None = None,
    use_rate_limiting: bool = True,
    use_retry: bool = True,
) -> list[Any]:
    """
    Executes multiple functions in parallel with rate limiting and retry logic.
    Specifically designed to handle LLM API rate limits gracefully.

    Args:
        functions_with_args: List of tuples each containing the function callable and a tuple of arguments.
        allow_failures: if set to True, then the function result will just be None
        max_workers: Max number of worker threads
        use_rate_limiting: Whether to use semaphore-based rate limiting
        use_retry: Whether to use exponential backoff retry for rate limit errors

    Returns:
        list: A list of results for each function.
    """
    # Limit workers to avoid overwhelming the API
    if max_workers is not None:
        workers = min(max_workers, len(functions_with_args))
    else:
        # Default to the configured concurrency limit for LLM API calls
        workers = min(LLM_API_CONCURRENCY_LIMIT, len(functions_with_args))

    if workers <= 0:
        return []

    def execute_with_limits(func: Callable, args: tuple, index: int) -> tuple[int, Any]:
        """Execute function with rate limiting and retry logic."""
        if use_rate_limiting:
            with _LLM_API_SEMAPHORE:
                if use_retry:
                    result = retry_with_exponential_backoff(func, args)
                else:
                    result = func(*args)
        else:
            if use_retry:
                result = retry_with_exponential_backoff(func, args)
            else:
                result = func(*args)
        return (index, result)

    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {
            executor.submit(execute_with_limits, func, args, i): i
            for i, (func, args) in enumerate(functions_with_args)
        }

        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                index_result, result = future.result()
                results.append((index_result, result))
            except Exception as e:
                logger.exception(f"Function at index {index} failed due to {e}")
                results.append((index, None))

                if not allow_failures:
                    raise

    results.sort(key=lambda x: x[0])
    return [result for index, result in results]


def run_functions_tuples_in_parallel(
    functions_with_args: list[tuple[Callable, tuple]],
    allow_failures: bool = False,
    max_workers: int | None = None,
) -> list[Any]:
    """
    Executes multiple functions in parallel and returns a list of the results for each function.

    Args:
        functions_with_args: List of tuples each containing the function callable and a tuple of arguments.
        allow_failures: if set to True, then the function result will just be None
        max_workers: Max number of worker threads

    Returns:
        dict: A dictionary mapping function names to their results or error messages.
    """
    workers = (
        min(max_workers, len(functions_with_args))
        if max_workers is not None
        else len(functions_with_args)
    )

    if workers <= 0:
        return []

    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_index = {
            executor.submit(func, *args): i
            for i, (func, args) in enumerate(functions_with_args)
        }

        for future in as_completed(future_to_index):
            index = future_to_index[future]
            try:
                results.append((index, future.result()))
            except Exception as e:
                logger.exception(f"Function at index {index} failed due to {e}")
                results.append((index, None))

                if not allow_failures:
                    raise

    results.sort(key=lambda x: x[0])
    return [result for index, result in results]


class FunctionCall(Generic[R]):
    """
    Container for run_functions_in_parallel, fetch the results from the output of
    run_functions_in_parallel via the FunctionCall.result_id.
    """

    def __init__(
        self, func: Callable[..., R], args: tuple = (), kwargs: dict | None = None
    ):
        self.func = func
        self.args = args
        self.kwargs = kwargs if kwargs is not None else {}
        self.result_id = str(uuid.uuid4())

    def execute(self) -> R:
        return self.func(*self.args, **self.kwargs)


def run_functions_in_parallel(
    function_calls: list[FunctionCall],
    allow_failures: bool = False,
) -> dict[str, Any]:
    """
    Executes a list of FunctionCalls in parallel and stores the results in a dictionary where the keys
    are the result_id of the FunctionCall and the values are the results of the call.
    """
    results = {}

    with ThreadPoolExecutor(max_workers=len(function_calls)) as executor:
        future_to_id = {
            executor.submit(func_call.execute): func_call.result_id
            for func_call in function_calls
        }

        for future in as_completed(future_to_id):
            result_id = future_to_id[future]
            try:
                results[result_id] = future.result()
            except Exception as e:
                logger.exception(f"Function with ID {result_id} failed due to {e}")
                results[result_id] = None

                if not allow_failures:
                    raise

    return results
