"""
GPT-5 Nano 간단 연결 예제
- python-dotenv로 .env에서 API 키 로드
- openai 패키지로 Chat Completions 호출
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일에서 환경변수 로드
load_dotenv()

# OpenAI 클라이언트 생성
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)


def chat(user_message: str) -> str:
    """GPT-5 Nano에게 메시지를 보내고 응답을 받는다."""
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content
"""
GPT-5 Nano 간단 연결 예제
- python-dotenv로 .env에서 API 키 로드
- openai 패키지로 Chat Completions 호출
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

# .env 파일에서 환경변수 로드
load_dotenv()

# OpenAI 클라이언트 생성
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
)


def chat(user_message: str) -> str:
    """GPT-5 Nano에게 메시지를 보내고 응답을 받는다."""
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": user_message},
        ],
    )
    return response.choices[0].message.content


if __name__ == "__main__":
    question = "파이썬에서 리스트와 튜플의 차이점을 간단히 설명해줘."
    print(f"질문: {question}\n")

    answer = chat(question)
    print(f"GPT-5 Nano 응답:\n{answer}")

if __name__ == "__main__":
    question = "파이썬에서 리스트와 튜플의 차이점을 간단히 설명해줘."
    print(f"질문: {question}\n")

    answer = chat(question)
    print(f"GPT-5 Nano 응답:\n{answer}")