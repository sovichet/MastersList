# encoding: utf-8

from __future__ import division, print_function, unicode_literals

import objc
from AppKit import NSNotificationCenter, NSImage, NSImageNameComputer
from Foundation import NSObject
from GlyphsApp import Glyphs, UPDATEINTERFACE, WINDOW_MENU
from GlyphsApp.plugins import GeneralPlugin

try:
    import vanilla
except ImportError:
    vanilla = None


class MasterList(GeneralPlugin):
    @objc.python_method
    def settings(self):
        self.name = "Masters List"

    @objc.python_method
    def start(self):
        from AppKit import NSMenuItem

        newMenuItem = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            self.name, self.showWindow_, ""
        )
        newMenuItem.setTarget_(self)
        Glyphs.menu[WINDOW_MENU].append(newMenuItem)

        self.w = None
        self._updatingSelection = False
        self._callbackRegistered = False
        self._step = 1
        self._groupAxisName = None
        self._groupButtonItems = None
        self._rowToMaster = []
        self._listDelegate = None

    # --- Menu action -----------------------------------------------------

    def showWindow_(self, sender):
        if vanilla is None:
            print(
                "MasterList: the vanilla module is required. "
                "Install it via Window > Plugin Manager > Modules."
            )
            return
        if self.w is None:
            self._buildPanel()
            self._subscribe()
            self._reload()
            self._syncSelectionFromFont()
            self.w.open()
        elif self.w.isVisible():
            self.w.hide()
        else:
            self._reload()
            self._syncSelectionFromFont()
            self.w.show()

    # --- UI construction -------------------------------------------------

    @objc.python_method
    def _buildPanel(self):
        self.w = vanilla.FloatingWindow((320, 360), "Masters", minSize=(280, 160))
        panel = self.w.getNSWindow()
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setHidesOnDeactivate_(True)

        self.w.prevButton = vanilla.Button(
            "auto", "←", callback=self.previousMasterCallback
        )
        self.w.nextButton = vanilla.Button(
            "auto", "→", callback=self.nextMasterCallback
        )
        self.w.stepLabel = vanilla.TextBox("auto", "🪜")
        self.w.stepField = vanilla.EditText(
            "auto",
            "%d" % self._step,
            callback=self.stepFieldCallback,
            continuous=False,
        )
        self.w.stepField.getNSTextField().setAlignment_(1)  # NSTextAlignmentCenter
        self.w.stepper = vanilla.Stepper(
            "auto",
            value=self._step,
            minValue=1,
            maxValue=999,
            increment=1,
            callback=self.stepperCallback,
        )
        self.w.groupButton = vanilla.PopUpButton(
            "auto",
            ["None"],
            callback=self.groupButtonCallback,
        )
        # the cache must match the fresh popup, or _updateGroupButton
        # will skip repopulating it after a close/reopen
        self._groupButtonItems = None

        columnDescriptions = [
            dict(
                title="",
                key="compat",
                editable=False,
                width=22,
                minWidth=22,
                maxWidth=30,
            ),
            dict(
                title="Name",
                key="name",
                editable=False,
                width=150,
                minWidth=80,
                maxWidth=600,
            ),
            dict(
                title="Axes",
                key="axes",
                editable=False,
                width=110,
                minWidth=40,
                maxWidth=600,
            ),
        ]
        self.w.list = vanilla.List(
            "auto",
            [],
            columnDescriptions=columnDescriptions,
            selectionCallback=self.listSelectionCallback,
            allowsMultipleSelection=False,
            allowsEmptySelection=True,
            allowsSorting=False,
            autohidesScrollers=True,
            rowHeight=21.0,
        )
        # Name takes all slack; compat/Axes keep their width (user-resizable)
        tableView = self.w.list.getNSTableView()
        tableView.setColumnAutoresizingStyle_(1)  # NSTableViewUniformColumnAutoresizingStyle
        for column in tableView.tableColumns():
            column.setResizingMask_(3 if column.identifier() == "name" else 2)  # user|auto vs user only

        self._listDelegate = _MasterListDelegate.alloc().initWithPlugin_(self)
        self.w.list.getNSTableView().setDelegate_(self._listDelegate)
        self.w.list.getNSTableView().setFloatsGroupRows_(True)

        rules = [
            "H:|-margin-[prevButton]-gap-[nextButton]"
            "-(>=gap)-[stepLabel]-gap-[stepField(==44)]-gap-[stepper]-gap-[groupButton]-margin-|",
            "H:|[list]|",
            "V:|-margin-[prevButton]-margin-[list]|",
            "V:|-margin-[nextButton]",
            "V:|-labelPad-[stepLabel]",
            "V:|-margin-[stepField]",
            "V:|-margin-[stepper]",
            "V:|-margin-[groupButton]",
        ]
        metrics = {"margin": 8, "gap": 4, "labelPad": 10}
        self.w.addAutoPosSizeRules(rules, metrics)

        self.w.bind("close", self.windowClosedCallback)

    # --- Notification subscription --------------------------------------

    @objc.python_method
    def _subscribe(self):
        if self._callbackRegistered:
            return
        Glyphs.addCallback(self.updateInterface_, UPDATEINTERFACE)
        nc = NSNotificationCenter.defaultCenter()
        nc.addObserver_selector_name_object_(
            self, self.documentChanged_, "GSDocumentActivateNotification", None
        )
        nc.addObserver_selector_name_object_(
            self, self.documentChanged_, "GSDocumentWasSavedSuccessfully", None
        )
        nc.addObserver_selector_name_object_(
            self, self.documentChanged_, "NSWindowDidBecomeKeyNotification", None
        )
        self._callbackRegistered = True

    @objc.python_method
    def _unsubscribe(self):
        if not self._callbackRegistered:
            return
        try:
            Glyphs.removeCallback(self.updateInterface_)
        except Exception:
            pass
        NSNotificationCenter.defaultCenter().removeObserver_(self)
        self._callbackRegistered = False

    def updateInterface_(self, sender):
        self._reload()
        self._syncSelectionFromFont()

    def documentChanged_(self, notification):
        self._reload()
        self._syncSelectionFromFont()

    @objc.python_method
    def windowClosedCallback(self, sender):
        self._unsubscribe()
        self.w = None
        self._listDelegate = None

    # --- Data helpers ----------------------------------------------------

    @objc.python_method
    def _currentFont(self):
        try:
            return Glyphs.font
        except Exception:
            return None

    @objc.python_method
    def _masters(self):
        font = self._currentFont()
        if font is None:
            return []
        try:
            return list(font.masters)
        except Exception:
            return []

    @objc.python_method
    def _axesString(self, font, master):
        try:
            axes = font.axes
        except Exception:
            axes = None
        if not axes:
            return ""
        try:
            values = list(master.axes)
        except Exception:
            values = []
        parts = []
        for i, axis in enumerate(axes):
            if i >= len(values):
                break
            try:
                tag = axis.axisTag
            except Exception:
                tag = "axis%d" % i
            value = values[i]
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            parts.append("%s %s" % (tag, value))
        return ", ".join(parts)

    @objc.python_method
    def _activeGlyph(self):
        font = self._currentFont()
        if font is None:
            return None
        try:
            layer = font.selectedLayers[0] if font.selectedLayers else None
        except Exception:
            layer = None
        if layer is None:
            return None
        try:
            return layer.parent
        except Exception:
            return None

    @objc.python_method
    def _compareString(self, layer):
        if layer is None:
            return None
        try:
            return layer.compareString()
        except Exception:
            pass
        try:
            return layer.compareString
        except Exception:
            return None

    @objc.python_method
    def _compatibilityFor(self, font, masterIndex):
        """Returns one of: 'self', 'match', 'mismatch', 'missing', 'none'."""
        glyph = self._activeGlyph()
        if glyph is None:
            return "none"
        masters = self._masters()
        if not (0 <= masterIndex < len(masters)):
            return "none"
        try:
            activeIndex = int(font.masterIndex)
        except Exception:
            activeIndex = 0
        try:
            activeMasterID = masters[activeIndex].id
            thisMasterID = masters[masterIndex].id
        except Exception:
            return "none"
        try:
            activeLayer = glyph.layers[activeMasterID]
            thisLayer = glyph.layers[thisMasterID]
        except Exception:
            return "missing"
        if activeLayer is None or thisLayer is None:
            return "missing"
        if masterIndex == activeIndex:
            return "self"
        activeCS = self._compareString(activeLayer)
        thisCS = self._compareString(thisLayer)
        if activeCS is None or thisCS is None:
            return "missing"
        return "match" if activeCS == thisCS else "mismatch"

    @objc.python_method
    def _compatSymbol(self, font, masterIndex):
        state = self._compatibilityFor(font, masterIndex)
        if state == "self":
            return "🔘"
        if state == "match":
            return "🟢"
        if state == "mismatch":
            return "🔴"
        return "—"

    @objc.python_method
    def _axisNames(self):
        font = self._currentFont()
        if font is None:
            return []
        try:
            axes = font.axes
        except Exception:
            return []
        names = []
        for i, axis in enumerate(axes):
            try:
                names.append(str(axis.axisTag))
            except Exception:
                names.append("Axis %d" % (i + 1))
        return names

    @objc.python_method
    def _groupAxisIndex(self):
        if self._groupAxisName is None:
            return None
        names = self._axisNames()
        if self._groupAxisName in names:
            return names.index(self._groupAxisName)
        return None

    @objc.python_method
    def _axisValue(self, master, axisIndex):
        try:
            return list(master.axes)[axisIndex]
        except Exception:
            return None

    @objc.python_method
    def _listRows(self):
        """Returns (items, rowToMaster). Header rows map to None."""
        font = self._currentFont()
        if font is None:
            return [dict(name="No font open", axes="", compat="")], [None]
        masters = self._masters()
        entries = []
        for i, master in enumerate(masters):
            try:
                name = master.name or ""
            except Exception:
                name = ""
            entries.append(
                (
                    i,
                    dict(
                        name=name,
                        axes=self._axesString(font, master),
                        compat=self._compatSymbol(font, i),
                    ),
                )
            )
        axisIndex = self._groupAxisIndex()
        if axisIndex is None:
            return [item for _, item in entries], [i for i, _ in entries]
        groups = {}
        for i, item in entries:
            value = self._axisValue(masters[i], axisIndex)
            groups.setdefault(value, []).append((i, item))
        items = []
        rowToMaster = []
        for value in sorted(groups, key=lambda v: (v is None, v or 0)):
            display = value
            if isinstance(display, float) and display.is_integer():
                display = int(display)
            header = "%s %s" % (
                self._groupAxisName,
                "—" if display is None else display,
            )
            items.append(dict(name=header, axes="", compat=""))
            rowToMaster.append(None)
            for i, item in groups[value]:
                items.append(item)
                rowToMaster.append(i)
        return items, rowToMaster

    @objc.python_method
    def _updateGroupButton(self):
        names = self._axisNames()
        buttonItems = ["None"] + names
        if buttonItems == self._groupButtonItems:
            return
        self._groupButtonItems = buttonItems
        self.w.groupButton.setItems(buttonItems)
        if self._groupAxisName in names:
            self.w.groupButton.set(names.index(self._groupAxisName) + 1)
        else:
            self._groupAxisName = None
            self.w.groupButton.set(0)

    @objc.python_method
    def _reload(self):
        if self.w is None:
            return
        self._updateGroupButton()
        items, self._rowToMaster = self._listRows()
        self._updatingSelection = True
        try:
            self.w.list.set(items)
        finally:
            self._updatingSelection = False

    @objc.python_method
    def _syncSelectionFromFont(self):
        if self.w is None:
            return
        font = self._currentFont()
        selection = []
        if font is not None:
            try:
                index = int(font.masterIndex)
            except Exception:
                index = -1
            if index in self._rowToMaster:
                selection = [self._rowToMaster.index(index)]
        self._updatingSelection = True
        try:
            self.w.list.setSelection(selection)
            if selection:
                self.w.list.scrollToSelection()
        finally:
            self._updatingSelection = False

    @objc.python_method
    def _selectMasterAtIndex(self, row):
        if self._updatingSelection:
            return
        font = self._currentFont()
        if font is None:
            return
        masters = self._masters()
        if not (0 <= row < len(masters)):
            return
        try:
            if int(font.masterIndex) == row:
                return
            font.masterIndex = row
        except Exception:
            pass

    @objc.python_method
    def listSelectionCallback(self, sender):
        if self._updatingSelection:
            return
        selection = sender.getSelection()
        if not selection:
            return
        row = selection[0]
        masterIndex = None
        if 0 <= row < len(self._rowToMaster):
            masterIndex = self._rowToMaster[row]
        if masterIndex is None:
            # header (or placeholder) row: bounce selection back to the master
            self._syncSelectionFromFont()
            return
        self._selectMasterAtIndex(masterIndex)
        self._reload()
        self._syncSelectionFromFont()

    @objc.python_method
    def groupButtonCallback(self, sender):
        names = self._axisNames()
        index = sender.get()
        if 1 <= index <= len(names):
            self._groupAxisName = names[index - 1]
        else:
            self._groupAxisName = None
        self._reload()
        self._syncSelectionFromFont()

    # --- Stepper / Prev / Next actions ----------------------------------

    @objc.python_method
    def _stepMaster(self, direction):
        font = self._currentFont()
        if font is None:
            return
        masters = self._masters()
        if not masters:
            return
        # master indices in visual list order (grouped or flat), headers skipped
        order = [i for i in self._rowToMaster if i is not None]
        if not order:
            order = list(range(len(masters)))
        try:
            current = int(font.masterIndex)
        except Exception:
            current = 0
        try:
            position = order.index(current)
        except ValueError:
            position = 0
        step = max(1, int(self._step)) * direction
        position = (position + step) % len(order)
        target = order[position]
        if target == current:
            return
        self._selectMasterAtIndex(target)
        self._reload()
        self._syncSelectionFromFont()

    @objc.python_method
    def previousMasterCallback(self, sender):
        self._stepMaster(-1)

    @objc.python_method
    def nextMasterCallback(self, sender):
        self._stepMaster(1)

    @objc.python_method
    def stepperCallback(self, sender):
        value = max(1, int(sender.get()))
        self._step = value
        self.w.stepField.set("%d" % value)

    @objc.python_method
    def stepFieldCallback(self, sender):
        try:
            value = int(sender.get())
        except (TypeError, ValueError):
            value = self._step
        value = max(1, value)
        self._step = value
        sender.set("%d" % value)
        self.w.stepper.set(value)

    # --- Standard plugin shims ------------------------------------------

    @objc.python_method
    def __file__(self):
        """Please leave this method unchanged"""
        return __file__

    def _sortID(self):
        return 0

    def setSortID_(self, value):
        pass

    def sortID(self):
        return 0

    def __del__(self):
        try:
            self._unsubscribe()
        except Exception:
            pass


# ----------------------------------------------------------------------
# Table delegate (group-row separators, selection gating)
# ----------------------------------------------------------------------


class _MasterListDelegate(NSObject):
    def initWithPlugin_(self, plugin):
        self = objc.super(_MasterListDelegate, self).init()
        if self is None:
            return None
        self.plugin = plugin
        return self

    def tableView_isGroupRow_(self, tableView, row):
        if self.plugin._currentFont() is None:
            return False
        rowToMaster = self.plugin._rowToMaster
        return 0 <= row < len(rowToMaster) and rowToMaster[row] is None

    def tableView_shouldSelectRow_(self, tableView, row):
        if self.plugin._currentFont() is None:
            return False
        rowToMaster = self.plugin._rowToMaster
        return 0 <= row < len(rowToMaster) and rowToMaster[row] is not None
