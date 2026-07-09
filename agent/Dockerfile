# AgentCore Runtime 用イメージ。src/ の explainer/store/line を import できるよう同梱する。
# AgentCore は ARM64 コンテナを要求するため platform を固定する。
FROM --platform=linux/arm64 python:3.12-slim

WORKDIR /app

COPY agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 図解ロジックは src/ 側にあるので同梱し、PYTHONPATH に載せる
COPY src/ ./src/
COPY agent/agent_runtime.py ./agent_runtime.py
ENV PYTHONPATH=/app/src

CMD ["python", "agent_runtime.py"]
