from locust import HttpUser, task, between

class MLServiceUser(HttpUser):
    wait_time = between(1, 2)

    @task(10)
    def predict(self):
        payload = {
            "name": "Greeting From Earth: ZGAC Arts Capsule For ET",
            "category": "Narrative Film",
            "main_category": "Film & Video",
            "currency": "USD",
            "deadline": "2017-11-01",
            "goal": 30000.0,
            "launched": "2017-09-02",
            "country": "US",
            "usd_goal_real": 30000.00
        }
        self.client.post(
            "/v1/predict",
            json=payload,
            name="/v1/predict"
        )

    @task(1)
    def health_check(self):
        self.client.get(
            "/health",
            name="/health"
        )