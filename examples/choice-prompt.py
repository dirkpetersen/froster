from rich.console import Console
from rich.prompt import Prompt, IntPrompt
from rich import box
from rich.table import Table
from rich.panel import Panel

console = Console()

def display_choices(choices):
    table = Table(box=box.SQUARE, show_header=False)
    table.add_column("Index")
    table.add_column("Choice")
    
    for index, choice in enumerate(choices, 1):
        table.add_row(f"{index}", choice)
    
    console.print(Panel.fit(table, title="Choices"))

def main():
    console.print("Welcome to the Colorful Python Prompt!", style="bold blue")
    choices = ["Choice 1", "Choice 2", "Choice 3", "Choice 4"]
    display_choices(choices)
    #selected_index = IntPrompt.ask("Please select a choice by entering its index:", min=1, max=len(choices))
    selected_index = IntPrompt.ask("Please select a choice by entering its index:")

    console.print(f"\nYou have selected: {choices[selected_index - 1]}", style="bold green")

if __name__ == "__main__":
    main()


