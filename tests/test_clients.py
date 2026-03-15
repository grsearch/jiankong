from app.clients import BirdeyeClient, HeliusClient


def test_birdeye_extract_holders_supports_nested_paths():
    value, path = BirdeyeClient._extract_holders_from_overview({"holders": "456"})
    assert value == 456
    assert path == "data.holders"

    nested_value, nested_path = BirdeyeClient._extract_holders_from_overview(
        {"tokenOverview": {"holderCount": 789.0}}
    )
    assert nested_value == 789
    assert nested_path == "data.tokenOverview.holderCount"


def test_birdeye_ignores_ambiguous_holder_field():
    value, path = BirdeyeClient._extract_holders_from_overview({"holder": 1})
    assert value is None
    assert path is None


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


def test_helius_extract_owner_compatible_keys():
    assert HeliusClient._extract_owner({"owner": "abc"}) == "abc"
    assert HeliusClient._extract_owner({"token_info": {"owner": "def"}}) == "def"
    assert HeliusClient._extract_owner({"tokenInfo": {"owner": "xyz"}}) == "xyz"
