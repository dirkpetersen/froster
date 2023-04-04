import csv
import io

from textual.app import App, ComposeResult
from textual.widgets import DataTable
from textual.message import Message

CSV = """lane,swimmer,country,time
4,Joseph Schooling,Singapore,50.39
2,Michael Phelps,United States,51.14
5,Chad le Clos,South Africa,51.14
6,László Cseh,Hungary,51.14
3,Li Zhuhao,China,51.26
8,Mehdy Metella,France,51.58
7,Tom Shields,United States,51.73
1,Aleksandr Sadovnikov,Russia,51.84"""


class TableApp(App):

    messages_to_record = {
        "RowHighlighted",
        "RowSelected",
        "HeaderSelected",
        "RowLabelSelected",
    }

    def __init__(self):
        super().__init__()
        self.messages = []

    def record_data_table_event(self, message: Message) -> None:
        name = message.__class__.__name__
        if name in self.messages_to_record:
            self.messages.append(message)

    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.cursor_type = "row"
        table.fixed_columns = 1
        table.fixed_rows = 1
        yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        rows = csv.reader(io.StringIO(CSV))
        table.add_columns(*next(rows))
        table.add_rows(rows)


    @property
    def message_names(self) -> list[str]:
        return [message.__class__.__name__ for message in self.messages]

    async def _on_message(self, message: Message) -> None:
        await super()._on_message(message)
        self.record_data_table_event(message)


if __name__ == "__main__":
    app = TableApp()
    app.run()
