from app.clients import BirdeyeClient, HeliusClient


def test_birdeye_extract_holders_supports_multiple_keys():
    assert BirdeyeClient._extract_holders_from_overview({"holder": 123}) == 123
    assert BirdeyeClient._extract_holders_from_overview({"holders": "456"}) == 456
    assert BirdeyeClient._extract_holders_from_overview({"holderCount": 789.0}) == 789
    assert BirdeyeClient._extract_holders_from_overview({"unknown": 1}) is None


def test_helius_extract_page_accounts_parses_shapes():
    payload = {
        "result": {
            "token_accounts": [{"owner": "w1"}, {"owner": "w2"}],
            "page": 1,
            "limit": 1000,
            "total": 2001,
        }
    }
    accounts, has_more = HeliusClient._extract_page_accounts(payload)
    assert len(accounts) == 2
    assert has_more is True

    payload_cursor = {"result": {"accounts": [{"owner": "w3"}], "cursor": "next_cursor"}}
    accounts2, has_more2 = HeliusClient._extract_page_accounts(payload_cursor)
    assert len(accounts2) == 1
    assert has_more2 is True
