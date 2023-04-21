def prompt_with_default(question, default_value=None, type_check=None):
    if default_value is not None:
        question += f" [default: {default_value}]"

    while True:
        user_input = input(f"\033[93m{question}\033[0m ")

        if not user_input:
            if default_value is not None:
                return default_value
            else:
                print("Please enter a value.")
        else:
            if type_check == 'number':
                try:
                    value = float(user_input)
                    return value
                except ValueError:
                    print("Invalid input. Please enter a number.")
            elif type_check == 'string':
                if not user_input.isnumeric():
                    return user_input
                else:
                    print("Invalid input. Please enter a string without numbers or special characters.")
            else:
                return user_input

if __name__ == "__main__":
    number_value = prompt_with_default("Please enter a number:", default_value=10, type_check='number')
    print(f"Number value: {number_value}")

    string_value = prompt_with_default("Please enter a string:", default_value="Hello", type_check='string')
    print(f"String value: {string_value}")

    any_value = prompt_with_default("Please enter any value:", default_value="Default")
    print(f"Any value: {any_value}")

