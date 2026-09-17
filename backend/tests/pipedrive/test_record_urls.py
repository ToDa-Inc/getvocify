from app.services.pipedrive.record_urls import (
    build_pipedrive_record_url,
    company_domain_from_api_domain,
)


def test_company_domain_from_api_domain():
    assert company_domain_from_api_domain("https://vocify2.pipedrive.com") == "vocify2"
    assert company_domain_from_api_domain("https://api.pipedrive.com") is None
    assert company_domain_from_api_domain("https://oauth.pipedrive.com") is None
    assert company_domain_from_api_domain(None) is None


def test_build_official_deal_and_person_urls():
    assert (
        build_pipedrive_record_url("vocify2", "deal", "222")
        == "https://vocify2.pipedrive.com/deal/222"
    )
    assert (
        build_pipedrive_record_url("vocify2", "person", "13")
        == "https://vocify2.pipedrive.com/person/13"
    )
    assert (
        build_pipedrive_record_url("vocify2", "contact", "13")
        == "https://vocify2.pipedrive.com/person/13"
    )
