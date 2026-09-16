import random


def main():
    answer = random.randint(1, 100)
    attempts = 0

    print("1부터 100 사이의 숫자를 맞춰보세요! (적은 횟수로 맞출수록 좋습니다)")

    while True:
        try:
            guess = int(input("숫자를 입력하세요: "))
        except ValueError:
            print("숫자만 입력해주세요.")
            continue

        attempts += 1

        if guess < answer:
            print("낮습니다.")
        elif guess > answer:
            print("높습니다.")
        else:
            print(f"축하합니다! {attempts}번 만에 정답 {answer}을(를) 맞추셨습니다!")
            break


if __name__ == "__main__":
    main()
