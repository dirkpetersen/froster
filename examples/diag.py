
from textual.app import App, ComposeResult
from textual.containers import Grid
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.screen import Screen
from textual.widgets import Static, Header, Footer, Button, Input, Label

class FrosterConfig(App):
    #CSS_PATH = "button.css"
    def compose(self) -> ComposeResult:
        #yield Header()
        yield Label("Hello, world!")
        #yield Horizontal(
        #     Button.success("Save"),
        #     Button.error("Cancel"),
        #)
        yield VerticalScroll(
	    Static("Fun Input", classes="header"),
	    Input(placeholder="AWS_KEY_ID_1"),
	    Input(placeholder="AWS_KEY_ID_2"),
	    Input(placeholder="AWS_KEY_ID_3"),
	    Input(placeholder="AWS_KEY_ID_4"),
	    Input(placeholder="AWS_KEY_ID_5"),
            Horizontal(
                Button.success("Save"),
                Button.error("Cancel"),
            )
        )
        #yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "continue":
            print("Moin")
        self.app.exit()
       
if __name__ == "__main__":
    app = FrosterConfig()
    app.run()

