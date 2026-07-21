"""Guards on the Browserbase helpers' shapes — a misplaced @asynccontextmanager
decorator once silently broke ALL cloud-browser description fetching (empty results,
no error). These catch that class of regression without hitting the network."""

import inspect

from src.browser import browserbase as bb


def test_create_session_is_a_plain_coroutine():
    # Must be awaitable (`bb, session = await create_session()`), NOT a context
    # manager. If @asynccontextmanager lands here, this flips to False.
    assert inspect.iscoroutinefunction(bb.create_session)


def test_connected_page_is_an_async_context_manager():
    # Must support `async with _connected_page() as page`. Calling it does NOT run
    # the body (that happens on __aenter__), so this touches no network.
    cm = bb._connected_page()
    assert hasattr(cm, "__aenter__") and hasattr(cm, "__aexit__")
