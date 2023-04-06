from textual.app import App, ComposeResult
from textual.widgets import Footer
from textual.containers import Container

class LayoutTest( App[ None ] ):

    CSS="""
    #left {
        width: 20%;
        height: 100%;
        dock: left;
        border: solid grey;
        background: #555;
    }

    #top {
        height: 20;
        dock: top;
        border: solid grey;
        background: #555;
    }

    #body {
        border: dashed red;
        background: yellow;
    }

    #bottom {
        height: 20;
        dock: bottom;
        border: solid grey;
        background: #555;
    }
    """

    def compose(self) -> ComposeResult:
        yield Container(
            Container(id="left"),
            Container(
                Container(id="top"),
                Container(id="body"),
                Container(id="bottom")
            )
        )
        yield Footer()


LayoutTest().run()

