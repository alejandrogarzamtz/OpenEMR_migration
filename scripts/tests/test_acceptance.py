import unittest
from unittest.mock import patch

from scripts.acceptance import run


class AcceptanceTest(unittest.TestCase):
    def response(self,url):
        headers={"X-Content-Type-Options":"nosniff","X-Frame-Options":"DENY","Cache-Control":"no-store","Strict-Transport-Security":"max-age=31536000"}
        if url.endswith("/health/ready"):return 200,{"status":"ready","release":"v1"},headers,.01
        if url.endswith("/openapi.json"):return 200,{"paths":{f"/route/{value}":{} for value in range(101)}},headers,.01
        return 200,{"status":"live"},headers,.01

    def test_passes_release_contract_and_bounded_load(self):
        with patch("scripts.acceptance.get",side_effect=self.response):result=run("https://ehr.example.org","v1",10)
        self.assertEqual(result["status"],"passed")

    def test_rejects_plain_http_and_release_mismatch(self):
        with patch("scripts.acceptance.get",side_effect=self.response):result=run("http://ehr.example.org","v2",1)
        self.assertEqual(result["status"],"failed");self.assertEqual(len(result["failures"]),2)


if __name__=="__main__":unittest.main()
