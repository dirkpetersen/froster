
def display_choices(choices):
    print("\nChoices:")
    for index, choice in enumerate(choices, 1):
        print(f"{index}. {choice}")

def main():
    print("Welcome to the Python Prompt!")

    choices = ["Choice 1", "Choice 2", "Choice 3", "Choice 4"]

    display_choices(choices)

    while True:
        try:
            selected_index = int(input("Please select a choice by entering its index: "))
            if 1 <= selected_index <= len(choices):
                break
            else:
                print(f"Invalid input. Please enter a number between 1 and {len(choices)}.")
        except ValueError:
            print(f"Invalid input. Please enter a number between 1 and {len(choices)}.")

    print(f"\nYou have selected: {choices[selected_index - 1]}")

if __name__ == "__main__":
    main()

