"""Provider-boundary tests: listing identity, unsupported assets and network failures."""
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from data_loader import DataError, search_stocks, validate_request


def test_search_preserves_exchange_identity_and_filters_non_equities():
    quotes = [
        {"symbol": "RELIANCE.NS", "longname": "Reliance Industries", "exchDisp": "NSE", "quoteType": "EQUITY"},
        {"symbol": "RELIANCE.BO", "shortname": "Reliance Industries", "exchange": "BSE", "quoteType": "EQUITY"},
        {"symbol": "RELIANCE.NS", "quoteType": "EQUITY"},
        {"symbol": "BTC-USD", "quoteType": "CRYPTOCURRENCY"},
        {"symbol": "AAPL MSFT", "quoteType": "EQUITY"},
        {"symbol": None, "quoteType": "EQUITY"},
        {"symbol": "SPY", "quoteType": "ETF"},
        {"symbol": "^NSEI", "quoteType": "INDEX"},
        None,
    ]
    with patch("data_loader.yf.Search", return_value=SimpleNamespace(quotes=quotes)):
        found = search_stocks("Reliance")
    assert [x["symbol"] for x in found] == ["RELIANCE.NS", "RELIANCE.BO", "SPY", "^NSEI"]
    assert [x["exchange"] for x in found[:2]] == ["NSE", "BSE"]
    assert found[0]["name"] == "Reliance Industries"


@pytest.mark.parametrize("query", ["", "   ", None, "a" * 101])
def test_bad_search_input_does_not_call_provider(query):
    with patch("data_loader.yf.Search") as provider, pytest.raises(DataError):
        search_stocks(query)
    provider.assert_not_called()


def test_search_errors_are_actionable_and_do_not_expose_provider_tracebacks():
    with patch("data_loader.yf.Search", side_effect=RuntimeError("internal response")):
        with pytest.raises(DataError, match="Enter ticker") as error:
            search_stocks("Apple")
    assert "internal response" not in str(error.value)


@pytest.mark.parametrize("response", [None, {"error": "bad response"}])
def test_bad_search_payload_is_not_reported_as_no_matches(response):
    with patch("data_loader.yf.Search", return_value=SimpleNamespace(quotes=response)):
        with pytest.raises(DataError, match="unexpected"):
            search_stocks("Apple")


def test_empty_search_is_not_replaced_by_demo_stocks():
    with patch("data_loader.yf.Search", return_value=SimpleNamespace(quotes=[])):
        assert search_stocks("Unlisted company") == []


def test_indian_ampersand_ticker_is_searchable_and_downloadable():
    quote = {"symbol": "M&M.NS", "longname": "Mahindra & Mahindra", "exchDisp": "NSE", "quoteType": "EQUITY"}
    with patch("data_loader.yf.Search", return_value=SimpleNamespace(quotes=[quote])):
        assert search_stocks("Mahindra")[0]["symbol"] == "M&M.NS"
    assert validate_request("m&m.ns", "2024-01-01", "2024-02-01")[0] == "M&M.NS"
