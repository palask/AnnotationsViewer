import os
import sys
import gi
import json

from zotero_annotations_exporter import annotations_exporter

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402


# Load JSON files
def load_json(filename) -> list:
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return []


# Save JSON files
def save_json(data, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# Create a group mapping (for easy lookup)
def create_group_mapping(groups):
    return {group["key"]: group["name"] for group in groups}


# Add group to annotation or note
def add_group_to_item(items, group_key, item_key):
    for item in items:
        if item["key"] == item_key:
            if "groups" not in item:
                item["groups"] = []
            if group_key not in item["groups"]:
                item["groups"].append(group_key)


class AnnotationNoteManager(Gtk.ApplicationWindow):
    def __init__(self, application, annotations: list, notes: list, groups: list):
        super().__init__(application=application, title="Annotations Viewer")
        self.set_default_size(800, 600)

        self.annotations = annotations
        self.notes = notes
        self.groups = groups
        self.group_mapping = create_group_mapping(groups)

        self.create_widgets()

    def create_widgets(self):
        # Vertical box to hold UI components
        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.set_child(vbox)
        vbox.set_margin_top(10)
        vbox.set_margin_bottom(10)
        vbox.set_margin_start(10)
        vbox.set_margin_end(10)

        self.create_filter_widgets(vbox)
        self.create_item_list_widgets(vbox)
        self.create_item_group_management_widgets(vbox)

    def create_filter_widgets(self, vbox):
        # Horizontal box for both group filter and search box
        filter_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        vbox.append(filter_hbox)

        # Type filter label
        self.type_filter_label = Gtk.Label(label="Filter by Type:")
        filter_hbox.append(self.type_filter_label)

        # Type filter dropdown
        self.type_filter_dropdown = Gtk.DropDown()
        self.type_filter_strings = Gtk.StringList()
        self.no_selected_type_filter_text = "All"
        self.type_filter_strings.append(self.no_selected_type_filter_text)
        self.annotations_type_filter_text = "Annotations"
        self.type_filter_strings.append(self.annotations_type_filter_text)
        self.notes_type_filter_text = "Notes"
        self.type_filter_strings.append(self.notes_type_filter_text)
        self.type_filter_dropdown.props.model = self.type_filter_strings
        self.type_filter_dropdown.connect(
            "notify::selected-item", self.on_type_filter_changed
        )
        self.type_filter_dropdown.set_hexpand(True)
        filter_hbox.append(self.type_filter_dropdown)

        spacer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        spacer.set_size_request(20, -1)
        filter_hbox.append(spacer)

        # Group filter label
        self.group_filter_label = Gtk.Label(label="Filter by Group:")
        filter_hbox.append(self.group_filter_label)

        # Group filter dropdown
        self.group_filter_dropdown = Gtk.DropDown()
        self.group_filter_strings = Gtk.StringList()
        self.no_selected_group_filter_text = "All"
        self.group_filter_strings.append(self.no_selected_group_filter_text)
        for group in self.groups:
            self.group_filter_strings.append(group["name"])
        self.group_filter_dropdown.props.model = self.group_filter_strings
        self.group_filter_dropdown.connect(
            "notify::selected-item", self.on_group_filter_changed
        )
        self.group_filter_dropdown.set_hexpand(True)
        filter_hbox.append(self.group_filter_dropdown)

        # Search box
        self.search_entry = Gtk.Entry()
        self.search_entry.set_placeholder_text("Search...")
        self.search_entry.connect("changed", self.on_search_changed)
        self.search_entry.set_hexpand(True)
        vbox.append(self.search_entry)

    def create_item_list_widgets(self, vbox):
        # Create a scrolled window for the listbox to make it scrollable
        scrolled_window = Gtk.ScrolledWindow()
        scrolled_window.set_policy(
            Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.ALWAYS
        )  # Vertical scroll, horizontal is automatic
        vbox.append(scrolled_window)

        # ListBox to display items (annotations and notes)
        self.listbox = Gtk.ListBox()
        self.listbox.set_vexpand(True)
        scrolled_window.set_child(self.listbox)

        # Update the listbox with data
        self.update_listbox()

    def create_item_group_management_widgets(self, vbox):
        # Add controls below the listbox
        controls_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        controls_hbox.set_homogeneous(False)
        vbox.append(controls_hbox)

        # Group selection dropdown
        self.group_item_dropdown = Gtk.DropDown()
        self.group_item_strings = Gtk.StringList()
        self.no_selected_group_item_text = "Select Group"
        self.group_item_strings.append(self.no_selected_group_item_text)
        for group in self.groups:
            self.group_item_strings.append(group["name"])
        self.group_item_dropdown.props.model = self.group_item_strings
        self.group_item_dropdown.connect(
            "notify::selected-item",
            self.on_group_item_changed,
        )
        controls_hbox.append(self.group_item_dropdown)
        self.group_item_dropdown.set_hexpand(True)

        # Button to add selected item to a group
        self.add_to_group_button = Gtk.Button(label="Add to Group")
        self.add_to_group_button.connect("clicked", self.on_add_to_group_clicked)
        controls_hbox.append(self.add_to_group_button)

        # Button to remove selected item from a group
        self.remove_from_group_button = Gtk.Button(label="Remove from Group")
        self.remove_from_group_button.connect(
            "clicked", self.on_remove_from_group_clicked
        )
        controls_hbox.append(self.remove_from_group_button)

        self.set_group_item_button_states()

        separator = Gtk.Separator()
        separator.set_orientation(Gtk.Orientation.VERTICAL)
        controls_hbox.append(separator)

        # Button to create a new group
        self.new_group_button = Gtk.Button(label="Create New Group")
        self.new_group_button.connect("clicked", self.on_create_new_group_clicked)
        controls_hbox.append(self.new_group_button)

    def get_group_names_from_keys(self, group_keys):
        """Given a list of group keys, return the corresponding group names."""
        group_names = []
        for key in group_keys:
            group = next((group for group in self.groups if group["key"] == key), None)
            if group:
                group_names.append(group["name"])
        return ", ".join(group_names) if group_names else ""

    def is_item_in_group(self, item, selected_group):
        """Check if an item is in the selected group."""
        # Convert the selected group name to its corresponding key
        group_key = next(
            (group["key"] for group in self.groups if group["name"] == selected_group),
            None,
        )

        if group_key:
            # Check if the group key is in the item's groups list
            return group_key in item.get("groups", [])
        return False

    def get_items_of_type(self, selected_type):
        """Get all items of the selected type."""
        if selected_type == self.no_selected_type_filter_text:
            return self.annotations + self.notes
        if selected_type == self.annotations_type_filter_text:
            return self.annotations
        elif selected_type == self.notes_type_filter_text:
            return self.notes
        else:
            raise NotImplementedError("Unknown item type")

    def on_filter_changed(self, widget):
        """Callback when the group filter changes."""
        self.update_listbox()

    def on_search_changed(self, widget):
        """Callback when the search box changes."""
        self.update_listbox()

    def update_listbox(self):
        """Update the listbox with annotations and notes based on filters and search."""
        self.listbox.remove_all()  # Clear the current listbox items

        filtered_items = []

        # Get selected type
        selected_type = self.type_filter_dropdown.props.selected_item.props.string

        # Get selected group
        selected_group = self.group_filter_dropdown.props.selected_item.props.string

        if selected_group == self.no_selected_group_filter_text:
            filtered_items = self.get_items_of_type(selected_type)
        else:
            filtered_items = [
                item
                for item in self.get_items_of_type(selected_type)
                if self.is_item_in_group(item, selected_group)
            ]

        # Get search text
        search_text = self.search_entry.get_text().lower()  # Case-insensitive search

        # Further filter by search term
        filtered_items = [
            item for item in filtered_items if self.search_matches(item, search_text)
        ]

        # Add filtered items to the ListBox
        for item in filtered_items:
            if "annotationText" in item:
                display_text = (
                    item["annotationText"].strip() if item["annotationText"] else ""
                )
                type = "A"
            else:
                display_text = item["note"].strip()
                type = "N"

            parent_title = (
                item["parentItem"]["title"] if "parentItem" in item else "N/A"
            )
            parent_authors = (
                item["parentItem"]["authors"] if "parentItem" in item else ""
            )

            # Retrieve group names from the group keys in 'groups'
            group_names = self.get_group_names_from_keys(item.get("groups", []))

            # Create a custom row
            row = Gtk.ListBoxRow()
            row.data = item
            row.set_margin_top(4)
            row.set_margin_bottom(4)

            def escape_markup(text):
                # Replace < and > with their HTML entities
                text = text.replace("<", "&lt;").replace(">", "&gt;")
                return text

            display_text = escape_markup(display_text)
            parent_title = escape_markup(parent_title)
            parent_authors = escape_markup(parent_authors)
            if parent_authors:
                parent_string = f"{parent_title} ({parent_authors})"
            else:
                parent_string = parent_title

            label = Gtk.Label(xalign=0)
            label.set_markup(
                f"<b>{display_text}</b>\n{parent_string}\n[{type}] {group_names}"
            )
            label.set_property("wrap", True)  # Enable line wrapping
            label.set_max_width_chars(70)  # Adjust the maximum width of the text

            row.set_child(label)
            self.listbox.append(row)

    def search_matches(self, item, search_text):
        """Check if the item matches the search text in parent_title, parent_authors, or display_text."""
        parent_title = item["parentItem"]["title"] if "parentItem" in item else ""
        parent_authors = item["parentItem"]["authors"] if "parentItem" in item else ""
        display_text = (
            item["annotationText"] if "annotationText" in item else item.get("note", "")
        )
        if display_text is None:
            display_text = ""

        # Check if any of the fields contain the search text
        return (
            search_text in parent_title.lower()
            or search_text in parent_authors.lower()
            or search_text in display_text.lower()
        )

    def on_type_filter_changed(self, dropdown, _pspec):
        """Handle the type filter change event."""
        self.update_listbox()

    def on_group_filter_changed(self, dropdown, _pspec):
        """Handle the group filter change event."""
        self.update_listbox()

    def set_group_item_button_states(self):
        selected_group = self.group_item_dropdown.props.selected_item.props.string
        if selected_group == self.no_selected_group_item_text:
            self.add_to_group_button.set_sensitive(False)
            self.remove_from_group_button.set_sensitive(False)
        else:
            self.add_to_group_button.set_sensitive(True)
            self.remove_from_group_button.set_sensitive(True)

    def on_group_item_changed(self, dropdown, _pspec):
        """Handle the group item selection change event."""
        self.set_group_item_button_states()

    def on_add_to_group_clicked(self, button):
        """Add the selected item to the selected group."""
        selected_item_row = self.listbox.get_selected_row()

        if selected_item_row:
            selected_item = (
                selected_item_row.data
            )  # Retrieve the item data from the row's data attribute

            # Get the selected group from the dropdown
            selected_group = self.group_item_dropdown.props.selected_item.props.string
            group_key = None
            for group in self.groups:
                if group["name"] == selected_group:
                    group_key = group["key"]
                    break

            if group_key:
                # Add the group key to the item (annotations or notes)
                item_key = selected_item["key"]
                add_group_to_item(self.annotations, group_key, item_key)
                add_group_to_item(self.notes, group_key, item_key)

                # Save updated annotations and notes
                save_json(self.annotations, "data/annotations.json")
                save_json(self.notes, "data/notes.json")

                # Update the listbox to reflect the change
                self.update_listbox()
            else:
                popover = Gtk.Popover()
                popover.set_child(
                    Gtk.Label(label="Error: Selected Group was not found!")
                )
                popover.set_parent(self.add_to_group_button)
                popover.popup()
        else:
            popover = Gtk.Popover()
            popover.set_child(Gtk.Label(label="Error: Select an item first!"))
            popover.set_parent(self.add_to_group_button)
            popover.popup()

    def on_remove_from_group_clicked(self, button):
        """Remove the selected item from the selected group."""
        selected_item_row = self.listbox.get_selected_row()

        if selected_item_row:
            # Get the index of the selected row
            row_index = self.listbox.index_of(selected_item_row)

            # Get the selected item (either annotation or note)
            selected_item = (
                self.annotations[row_index]
                if "annotationText" in self.annotations[row_index]
                else self.notes[row_index]
            )

            # Get the selected group name from the combo box
            selected_group = self.group_item_dropdown.props.selected_item.props.string

            if selected_group != "Select Group":
                # Find the group key using the selected group name
                group_key = next(
                    group["key"]
                    for group in self.groups
                    if group["name"] == selected_group
                )
                print(
                    f"Removing selected item from group: {selected_group} (group key: {group_key})"
                )

                # Remove the group key from the selected item's 'groups' list
                if "groups" in selected_item and group_key in selected_item["groups"]:
                    selected_item["groups"].remove(group_key)

                    # Optionally, save changes to JSON
                    save_json(self.annotations, "data/annotations.json")
                    save_json(self.notes, "data/notes.json")

                    # Refresh the listbox after removing the group
                    self.update_listbox()

        else:
            popover = Gtk.Popover()
            popover.set_child(Gtk.Label(label="Error: Select an item first!"))
            popover.set_parent(self.remove_from_group_button)
            popover.popup()

    def on_create_new_group_clicked(self, button):
        """Create a new group by asking for user input."""

        def on_ok_button_clicked(button):
            new_group_name = entry.get_text()
            if new_group_name:
                # Create a new group and add to the group list
                new_group_key = (
                    f"group{len(self.groups) + 1}"  # Generate a new group key
                )
                new_group = {"key": new_group_key, "name": new_group_name}
                self.groups.append(new_group)
                self.group_mapping[new_group_key] = new_group_name

                # Update group filter and group combo boxes
                self.group_filter_strings.append(new_group_name)
                self.group_item_strings.append(new_group_name)

                # Save the updated groups list to groups.json
                save_json(self.groups, "data/groups.json")

                # Update the listbox
                self.update_listbox()

            dialog.close()

        dialog = Gtk.Dialog(title="Create New Group", transient_for=self)
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        content_box.set_margin_top(10)
        content_box.set_margin_start(10)
        content_box.set_margin_end(10)

        # Add a text entry to input the new group name
        entry = Gtk.Entry()
        entry.set_placeholder_text("Group Name")
        content_box.append(entry)
        dialog.get_child().append(content_box)

        # Create a box for the buttons at the bottom
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        button_box.set_margin_top(10)
        button_box.set_margin_bottom(10)
        button_box.set_halign(Gtk.Align.CENTER)
        dialog.get_child().append(button_box)

        # Create the Cancel button
        cancel_button = Gtk.Button(label="Cancel")
        cancel_button.connect("clicked", lambda button: dialog.close())
        button_box.append(cancel_button)

        # Create the OK button
        ok_button = Gtk.Button(label="OK")
        ok_button.connect("clicked", on_ok_button_clicked)
        button_box.append(ok_button)

        dialog.set_default_size(300, 100)
        dialog.present()


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="org.palask.AnnotationsViewer")
        self.annotations = load_json("data/annotations.json")
        self.notes = load_json("data/notes.json")
        self.groups = load_json("data/groups.json")

    def do_activate(self):
        # Create and show the window when the application is activated
        window = AnnotationNoteManager(self, self.annotations, self.notes, self.groups)
        window.set_visible(True)


if __name__ == "__main__":
    run_update = "update" in sys.argv
    exporter_exit_code = 0

    if run_update or not os.path.exists("data/"):
        exporter_exit_code = annotations_exporter()

    if exporter_exit_code == 0:
        app = Application()
        app.run()
    else:
        print("Could not load the annotations data. Please check your .env")
