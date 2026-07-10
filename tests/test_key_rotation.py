from fastapi.testclient import TestClient
import os
import uuid
from main import app

client = TestClient(app)


def test_rotate_returns_new_key_and_expiration(test_customer):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    response = client.post("/v1/keys/rotate", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["api_key"] 
    assert body["grace_period_expires_at"]  

def test_current_key_works(test_customer):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    response = client.post("/v1/keys/rotate", headers=auth_headers)
    assert response.status_code == 200
    new_api_key = response.json()["api_key"]
    
    new_auth_headers = {"Authorization": f"Bearer {new_api_key}"}
    subs_response = client.get("/v1/subscriptions", headers=new_auth_headers)
    assert subs_response.status_code == 200



def test_previous_key_works_during_grace_period(test_customer):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    response = client.post("/v1/keys/rotate", headers=auth_headers)
    new_api_key = response.json()["api_key"]
    test_authenticated_response = client.get("/v1/subscriptions", headers=auth_headers)
    assert test_authenticated_response.status_code == 200

def test_previous_key_fails_after_grace_period(test_customer):
    api_key = test_customer["api_key"]
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    response = client.post("/v1/keys/rotate", headers=auth_headers, json={"grace_period_seconds": 0})
    new_api_key = response.json()["api_key"]
    test_authenticated_response = client.get("/v1/subscriptions", headers=auth_headers)
    assert test_authenticated_response.status_code == 401


def test_second_rotation_invalidates_first_grace_period(test_customer):
    key_a = test_customer["api_key"]
    auth_headersA = {"Authorization": f"Bearer {key_a}"}
    response1 = client.post(f"/v1/keys/rotate", headers=auth_headersA)
    key_b = response1.json()["api_key"]
    auth_headersB = {"Authorization": f"Bearer {key_b}"}
    response2 = client.post(f"/v1/keys/rotate", headers=auth_headersB)
    key_c = response2.json()["api_key"]
    test_authenticated_response1 = client.get("/v1/subscriptions", headers=auth_headersA)
    assert test_authenticated_response1.status_code == 401
    test_authenticated_response2 = client.get("/v1/subscriptions", headers=auth_headersB)
    assert test_authenticated_response2.status_code == 200
