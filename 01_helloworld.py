import requests

response = requests.get("http://www.naver.com")
print(response.text)