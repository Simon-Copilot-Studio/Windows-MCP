INTERACTIVE_CONTROL_TYPE_NAMES = set(
    [
        "ButtonControl",
        "ListItemControl",
        "MenuItemControl",
        "EditControl",
        "CheckBoxControl",
        "RadioButtonControl",
        "ComboBoxControl",
        "HyperlinkControl",
        "SplitButtonControl",
        "TabItemControl",
        "TreeItemControl",
        "DataItemControl",
        "HeaderItemControl",
        "TextBoxControl",
        "SpinnerControl",
        "ScrollBarControl",
    ]
)

INTERACTIVE_ROLES = {
    # Buttons
    "PushButton",
    "SplitButton",
    "ButtonDropDown",
    "ButtonMenu",
    "ButtonDropDownGrid",
    "OutlineButton",
    # Links
    "Link",
    # Inputs & Selection
    "Text",
    "IpAddress",
    "HotkeyField",
    "ComboBox",
    "DropList",
    "CheckButton",
    "RadioButton",
    # Menus & Tabs
    "MenuItem",
    "ListItem",
    "PageTab",
    # Trees
    "OutlineItem",
    # Values
    "Slider",
    "SpinButton",
    "Dial",
    "ScrollBar",
    "Grip",
    # Grids
    "ColumnHeader",
    "RowHeader",
    "Cell",
}

DOCUMENT_CONTROL_TYPE_NAMES = set(["DocumentControl"])

STRUCTURAL_CONTROL_TYPE_NAMES = set([
    "PaneControl",
    "GroupControl",
    "CustomControl",
    "ToolBarControl",
    "TabControl",
    "MenuBarControl",
])

INFORMATIVE_CONTROL_TYPE_NAMES = set(
    [
        "TextControl",
        "ImageControl",
        "StatusBarControl",
        # 'ProgressBarControl',
        # 'ToolTipControl',
        # 'TitleBarControl',
        # 'SeparatorControl',
        # 'HeaderControl',
        # 'HeaderItemControl',
    ]
)

TEXT_CONTROL_TYPE_NAMES = set(["TextControl", "ImageControl"])

TEXT_OWNING_CONTROL_TYPE_NAMES = set([
    "ButtonControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "MenuItemControl",
    "TabItemControl",
    "HyperlinkControl",
    "ComboBoxControl",
    "EditControl",
    "ListItemControl",
    "HeaderItemControl",
    "TreeItemControl",
    "DataItemControl",
])

DEFAULT_ACTIONS = set(["Click", "Press", "Jump", "Check", "Uncheck", "Double Click"])

THREAD_MAX_RETRIES = 3
