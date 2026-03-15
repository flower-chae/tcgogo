### langchain에서 만든 ai 하네스 deepagent 를 이용해서 사용자가 requirement / SRS / PRD 를 입력하면 testcase 를 만들어주는 ai를 만든다
#### 이때 입력한 requirement / SRS / PRD 를 충족할 만한 TestCase가 나왔는지 검토를 해야한다. 
#### 이때 입력한 requirement / SRS / PRD 에서 원자? FR? 이 될만한걸 먼저 뽑아내는 탭을 만들고 그 탭의 내용으로부터 TestCase를 생성한다. 
#### FR/NFR 탭 -> 거기로부터 TestCase 생성
#### Deepagent를 공부하려는  목적이 크므로 Deepagent를 꼭 사용한다 
#### 모델은 gpt-5-nano를 사용하되 Tool 호출이 잘 안되면 gpt-5-mini, gpt-4.1, gpt-4o 같은걸 시도해 봐도 된다. 
#### 공부가 목적이므로 주석을 잘 충분히 달아준다. 
#### 적용한 skills 가 langchain에서 제공한 공식 skills 이다. 이걸 사용해야 성공률이 높다고 하니 이걸 이용한다. 


- backend : fastapi+deepagent (uv로 패키지 다운), 
    - 기본적인 skeleton이 있고 이곳에서 시작하면 됩니다.
    - 사용할 포트 : 3480
    - sqlalchemy 사용하지 말것 db 컨트롤하는데
- frontend : nuxt4 + nuxt-ui + pinia 사용 
    -  nuxt4설치 참조 : https://nuxt.com/docs/4.x/getting-started/installation
    - 사용할 포트 : 3482
    - 채팅창에서 

- db : PostgreSQL (deepagent의 memory 기능은 여기다 저장할것)

- 현재 작업 PC : 우분투 

- 내가 알아야 할 사항을 작업하는 틈틈히 : teach.md 로 저장할것