

import csv
import io

from textual.app import App, ComposeResult
from textual.widgets import DataTable

CSV = """id,GB,avg(MB),folder
1,213,5,/home/groups/test/folder2/main
2,180,140,/home/groups/test/folder1/temp
3,140,190,/home/groups/test/folder5
4,99,10003,/home/groups/test/folder3/other
5,54,6,/home/groups/test/folder4/data
"""

class TableApp(App[list]):
    def compose(self) -> ComposeResult:
        table = DataTable()
        table.focus()
        table.cursor_type = "row"
        #table.fixed_columns = 1
        #table.fixed_rows = 1
        yield table

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        rows = csv.reader(io.StringIO(CSV))
        table.add_columns(*next(rows))
        table.add_rows(rows)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        self.exit(self.query_one(DataTable).get_row(event.row_key))

if __name__ == "__main__":
    app = TableApp()
    print(app.run())
