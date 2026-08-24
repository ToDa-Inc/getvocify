from app.services.admin_accounts import assemble_account_list_items

USER = "11111111-1111-1111-1111-111111111111"


def test_assemble_list_item_joins_email_crm_and_memo_counts():
    items = assemble_account_list_items(
        profiles=[
            {
                "id": USER,
                "full_name": "Ada",
                "company_name": "Acme",
                "phone": "+1555",
                "created_at": "2026-01-01T00:00:00+00:00",
            }
        ],
        auth_users=[
            {
                "id": USER,
                "email": "ada@acme.com",
                "last_sign_in_at": "2026-08-01T00:00:00+00:00",
            }
        ],
        connections=[
            {
                "user_id": USER,
                "provider": "hubspot",
                "status": "connected",
                "token_expires_at": "2026-09-01T00:00:00+00:00",
            }
        ],
        memos=[
            {"user_id": USER, "status": "approved", "created_at": "2026-08-20T00:00:00+00:00"},
            {"user_id": USER, "status": "failed", "created_at": "2026-08-19T00:00:00+00:00"},
        ],
    )
    assert len(items) == 1
    row = items[0]
    assert row["email"] == "ada@acme.com"
    assert row["memo_count"] == 2
    assert row["approved_count"] == 1
    assert row["failed_count"] == 1
    assert row["last_memo_at"] == "2026-08-20T00:00:00+00:00"
    assert row["crm"][0]["provider"] == "hubspot"


def test_assemble_list_item_without_auth_row_has_empty_email():
    items = assemble_account_list_items(
        profiles=[
            {
                "id": USER,
                "full_name": None,
                "company_name": None,
                "phone": None,
                "created_at": "",
            }
        ],
        auth_users=[],
        connections=[],
        memos=[],
    )
    assert items[0]["email"] == ""
    assert items[0]["memo_count"] == 0
    assert items[0]["crm"] == []
