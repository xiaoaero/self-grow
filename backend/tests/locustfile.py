"""
Self Grow — Locust 压测脚本
用法: locust -f locustfile.py --host=http://localhost:3001
然后打开 http://localhost:3002 配置并发数并启动
"""

from locust import HttpUser, task, between
import random


class SelfGrowUser(HttpUser):
    """模拟普通用户操作：读多写少"""
    wait_time = between(0.5, 2)

    def on_start(self):
        """每个虚拟用户初始化时获取自身 user_id"""
        self.user_id = random.choice([1, 2])  # test=1, admin=2

    # ---- 高频读操作 ----

    @task(5)
    def get_profile(self):
        self.client.get(f"/api/users/profile?user_id={self.user_id}")

    @task(4)
    def get_habits(self):
        self.client.get(f"/api/habits?user_id={self.user_id}")

    @task(3)
    def get_tasks(self):
        self.client.get(f"/api/tasks?user_id={self.user_id}")

    @task(3)
    def get_actions(self):
        self.client.get(f"/api/actions?user_id={self.user_id}&limit=20&offset=0")

    @task(2)
    def get_goals(self):
        self.client.get(f"/api/goals?user_id={self.user_id}")

    @task(2)
    def get_rewards(self):
        self.client.get(f"/api/rewards?user_id={self.user_id}")

    @task(2)
    def get_stats_profile(self):
        self.client.get(f"/api/stats/profile?user_id={self.user_id}")

    @task(1)
    def get_today_stats(self):
        self.client.get(f"/api/actions/today-stats?user_id={self.user_id}")

    @task(1)
    def get_activity_feed(self):
        self.client.get(f"/api/activities/feed?user_id={self.user_id}")

    # ---- 低频写操作 ----

    @task(1)
    def toggle_habit(self):
        """习惯打卡（写操作，SQLite 瓶颈点）"""
        self.client.post(
            f"/api/habits/{random.randint(1,5)}/toggle",
        )

    @task(1)
    def create_action(self):
        """创建行动记录（写操作）"""
        self.client.post(
            f"/api/actions?user_id={self.user_id}",
            json={
                "name": "压测 - 学习",
                "category": "study",
                "duration_minutes": 30,
                "note": "自动化压测",
            },
        )


class SelfGrowWriteHeavyUser(HttpUser):
    """模拟写入密集型用户"""
    wait_time = between(0.1, 0.5)

    def on_start(self):
        self.user_id = random.choice([1, 2])

    @task(5)
    def create_action(self):
        self.client.post(
            f"/api/actions?user_id={self.user_id}",
            json={
                "name": f"压测行动-{random.randint(1, 9999)}",
                "category": random.choice(
                    ["health", "study", "work", "create", "relation", "finance", "hobby", "soul"]
                ),
                "duration_minutes": random.randint(5, 120),
                "note": "写压测",
            },
        )

    @task(3)
    def toggle_habit(self):
        self.client.post(
            f"/api/habits/{random.randint(1,5)}/toggle",
        )

    @task(2)
    def get_profile(self):
        self.client.get(f"/api/users/profile?user_id={self.user_id}")

    @task(1)
    def sync_stats(self):
        self.client.post(
            f"/api/users/stats/sync?user_id={self.user_id}",
            json={
                "today_focus": "压测",
                "tasks_completed": random.randint(0, 5),
                "habits_done": random.randint(0, 3),
                "exp_earned": random.randint(10, 100),
            },
        )
