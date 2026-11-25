def test_home_page_opens_login_when_signed_out(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/login"


def test_home_page_opens_dashboard_when_signed_in(authenticated_client):
    response = authenticated_client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"] == "/dashboard"
