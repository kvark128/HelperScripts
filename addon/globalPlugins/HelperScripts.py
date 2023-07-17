# Copyright (C) 2021 - 2023 Alexander Linkov <kvark128@yandex.ru>
# This file is covered by the GNU General Public License.
# See the file COPYING.txt for more details.
# Ukrainian Nazis and their accomplices are not allowed to use this plugin. Za pobedu!

import wx
import threading
import collections

import globalPluginHandler
import addonHandler
import ui
import tones
import globalVars
import scriptHandler
import api
import characterProcessing
import config
import winUser
import textInfos
import gui
import gui.logViewer
from controlTypes import Role, State
from speech import speech
from scriptHandler import script

addonHandler.initTranslation()
SPEECH_BUFFER_MAX_LENGTH = 300

class TextWindow(wx.Frame):

	def __init__(self, text, title, readOnly=True, insertionPoint=0):
		super(TextWindow, self).__init__(gui.mainFrame, title=title)
		sizer = wx.BoxSizer(wx.VERTICAL)
		style = wx.TE_MULTILINE | wx.TE_RICH
		if readOnly:
			style |= wx.TE_READONLY
		self.outputCtrl = wx.TextCtrl(self, style=style)
		self.outputCtrl.Bind(wx.EVT_KEY_DOWN, self.onOutputKeyDown)
		sizer.Add(self.outputCtrl, proportion=1, flag=wx.EXPAND)
		self.SetSizer(sizer)
		sizer.Fit(self)
		self.outputCtrl.SetValue(text)
		self.outputCtrl.SetFocus()
		self.outputCtrl.SetInsertionPoint(insertionPoint)
		self.Raise()
		self.Maximize()
		self.Show()

	def onOutputKeyDown(self, event):
		if event.GetKeyCode() == wx.WXK_ESCAPE:
			self.Close()
		event.Skip()

class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Helper Scripts")

	def __init__(self):
		super(GlobalPlugin, self).__init__()
		self._lastProgressBarValue = "0%"
		self._lastTooltip = None
		self._speechBuffer = []
		speech.speak = self._speechDecorator(speech.speak)

	def _speechDecorator(self, speakFunc):
		def wrapper(speechSequence, *args, **kwargs):
			if isinstance(speechSequence, collections.abc.Generator):
				speechSequence = [i for i in speechSequence]
			speakText = " ".join([s for s in speechSequence if isinstance(s, str)])
			if len(self._speechBuffer) >= SPEECH_BUFFER_MAX_LENGTH:
				del self._speechBuffer[0]
			self._speechBuffer.append(speakText)
			return speakFunc(speechSequence, *args, **kwargs)
		return wrapper

	def event_show(self, obj, nextHandler):
		if obj.role == Role.TOOLTIP:
			self._lastTooltip = obj.name
		nextHandler()

	def event_gainFocus(self, obj, nextHandler):
		self._lastTooltip = None
		nextHandler()

	def event_valueChange(self, obj, nextHandler):
		if obj.role == Role.PROGRESSBAR:
			self._lastProgressBarValue = obj.value
		nextHandler()

	def _get_selectedText(self):
		obj = api.getCaretObject()
		try:
			info = obj.makeTextInfo(textInfos.POSITION_SELECTION)
		except (RuntimeError, NotImplementedError):
			return None
		if not info.isCollapsed:
			return info.text

	def _saveScreenshot(self, bmp, default_filename):
		if not default_filename:
			default_filename = "screenshot"
		default_filename += ".png"

		gui.mainFrame.prePopup()
		filename = wx.FileSelector(_("Save screenshot as..."), default_filename=default_filename, flags=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
		gui.mainFrame.postPopup()

		if filename:
			bmp.SaveFile(filename, wx.BITMAP_TYPE_PNG)

	@script(description=_("Copies the last spoken phrase to the clipboard"))
	def script_copyPhrase(self, gesture):
		if len(self._speechBuffer) == 0:
			return
		text = self._speechBuffer[-1]
		if scriptHandler.getLastScriptRepeatCount() == 0:
			text = text.strip()
		api.copyToClip(text)
		tones.beep(200, 50)

	@script(description=_("Shows the NVDA log viewer"))
	def script_showLogViewer(self, gesture):
		if not globalVars.appArgs.secure:
			gui.logViewer.activate()

	@script(description=_("Reports the name and version of the application. Double-click to copy this information to the clipboard"))
	def script_appInfo(self, gesture):
		obj = api.getFocusObject()
		try:
			productName = obj.appModule.productName
			productVersion = obj.appModule.productVersion
		except Exception:
			ui.message(_("No application information"))
			return
		msg = f"{productName} {productVersion}"
		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(msg)
		else:
			api.copyToClip(msg)
			ui.message(_("Copied to clipboard"))

	@script(description=_("Reports value of the current navigator object. When you double-press, copy this value to clipboard"))
	def script_reportObjectValue(self, gesture):
		obj = api.getNavigatorObject()
		if not obj.value:
			ui.message(_("No value"))
			return

		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(obj.value)
		else:
			api.copyToClip(obj.value)
			ui.message(_("Copied to clipboard"))

	@script(description=_("Toggles the level of punctuation back"))
	def script_cycleSpeechSymbolLevel(self, gesture):
		curLevel = config.conf["speech"]["symbolLevel"]
		for level in characterProcessing.CONFIGURABLE_SPEECH_SYMBOL_LEVELS[-1::-1]:
			if level < curLevel:
				break
		else:
			level = characterProcessing.SymbolLevel.ALL

		name = characterProcessing.SPEECH_SYMBOL_LEVEL_LABELS[level]
		config.conf["speech"]["symbolLevel"] = level
		ui.message(_("symbol level %s") % name)

	@script(description=_("Opens a dialog containing the text of the currently focused window for easy review"))
	def script_windowVirtualViewer(self, gesture):
		obj = api.getFocusObject()
		if obj.role != Role.TERMINAL:
			obj = api.getForegroundObject().parent
		try:
			info = obj.makeTextInfo(textInfos.POSITION_ALL)
			text = info.clipboardText.strip()
		except Exception:
			text = None

		if not text:
			ui.message(_("No text"))
			return

		TextWindow(text, _("Virtual Viewer"))

	@script(description=_("Reports the number of characters and words in selected text or text from the clipboard. Double pressing reports the text itself. Triple pressing opens a separate window with that text"))
	def script_counterWordsAndSymbols(self, gesture):
		text = self.selectedText
		source = _("selection")
		if not text:
			text = api.getClipData()
			source = _("clipboard")
			if not text:
				ui.message(_("No text"))
				return

		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(_("{}/{} {}").format(len(text), len(text.split()), source))
		elif scriptHandler.getLastScriptRepeatCount() == 1:
			ui.message(text)
		else:
			TextWindow(text, _("Text"), readOnly=False)

	@script(description=_("Toggles between the speech modes of off and talk. When set to off NVDA will not speak anything. If talk then NVDA wil just speak normally."))
	def script_speechMode(self, gesture):
		curMode = speech.getState().speechMode
		if curMode != speech.SpeechMode.talk:
			speech.setSpeechMode(speech.SpeechMode.talk)
			ui.message(_("talk"))
		else:
			ui.message(_("off"))
			speech.setSpeechMode(speech.SpeechMode.off)

	@script(description=_("Reports clipboard text. Double pressing to read it for the characters. Triple pressing opens a separate window with this text"))
	def script_reportClipboardText(self, gesture):
		try:
			text = api.getClipData()
			if not text: raise OSError
		except OSError:
			ui.message(_("No text"))
			return

		repeat = scriptHandler.getLastScriptRepeatCount()
		if repeat == 0:
			ui.message(text)
		elif repeat == 1:
			speech.speakSpelling(text)
		elif repeat == 2:
			TextWindow(text, _("Clipboard text"), readOnly=False)

	@script(description=_("Makes click in the point of review cursor"))
	def script_click(self, gesture):
		info = api.getReviewPosition()
		try:
			curPoint = info.pointAtStart
		except (NotImplementedError, LookupError):
			ui.message(_("no point"))
			return
		api.setMouseObject(info.obj)
		winUser.setCursorPos(curPoint.x, curPoint.y)
		winUser.mouse_event(winUser.MOUSEEVENTF_LEFTDOWN, 0, 0, None, None)
		winUser.mouse_event(winUser.MOUSEEVENTF_LEFTUP, 0, 0, None, None)

	@script(description=_("Reports a selected text. Double pressing to read it for the characters"))
	def script_currentSelection(self, gesture):
		text = self.selectedText
		if text is None:
			ui.message(_("No selection"))
			return

		if scriptHandler.getLastScriptRepeatCount() == 0:
			ui.message(text)
		else:
			speech.speakSpelling(text)

	@script(description=_("Makes a screenshot of the current Navigator object"))
	def script_screenshot(self, gesture):
		if globalVars.appArgs.secure: return

		obj = api.getNavigatorObject()
		if State.OFFSCREEN in obj.states:
			ui.message(_("off screen"))
			return

		try:
			x, y, width, height = obj.location
		except Exception:
			ui.message(_("object has no location"))
			return

		bmp = wx.Bitmap(width, height)
		mem = wx.MemoryDC(bmp)
		mem.Blit(0, 0, width, height, wx.ScreenDC(), x, y)

		name = obj.role.displayString
		wx.CallAfter(self._saveScreenshot, bmp, name)

	@script(description=_("Reporting position of the element in the group"))
	def script_positionInfo(self, gesture):
		obj = api.getFocusObject()
		try:
			indexInGroup = obj.positionInfo["indexInGroup"]
			similarItemsInGroup = obj.positionInfo["similarItemsInGroup"]
			ui.message(_("{0} of {1}").format(indexInGroup, similarItemsInGroup))
		except KeyError:
			ui.message(_("no position"))

	@script(description=_("Selects or copies the text under the review cursor"))
	def script_simpleSelection(self, gesture):
		reviewPos = api.getReviewPosition()

		if not getattr(reviewPos.obj, "_copyStartMarker", None):
			reviewPos.obj._copyStartMarker = reviewPos.copy()
			ui.message(_("Start marked"))
			return

		startMarker = reviewPos.obj._copyStartMarker

		if reviewPos.compareEndPoints(startMarker, "endToEnd") > 0: # user has moved the cursor 'forward'
			startMarker.setEndPoint(reviewPos, "endToEnd")
		else: # user has moved the cursor 'backwards' or not at all.
			startMarker.setEndPoint(reviewPos, "startToStart")

		startMarker.move(textInfos.UNIT_CHARACTER, 1, endPoint="end")

		# for applications such as word, where the selected text is not automatically spoken we must monitor it ourself
		try:
			oldInfo = reviewPos.obj.makeTextInfo(textInfos.POSITION_SELECTION)
		except (RuntimeError, NotImplementedError):
			pass

		try:
			startMarker.updateSelection()
			if hasattr(reviewPos.obj, "reportSelectionChange"):
				# wait for applications such as word to update their selection so that we can detect it
				try:
					reviewPos.obj.reportSelectionChange(oldInfo)
				except Exception:
					pass
		except NotImplementedError:
			if startMarker.copyToClipboard():
				ui.message(_("Copied to clipboard"))
			else:
				ui.message(_("Unable to copy"))
		finally:
			reviewPos.obj._copyStartMarker = None

	@script(description=_("Reports the last value of the progress bar"))
	def script_reportLastProgressBarValue(self, gesture):
		ui.message(self._lastProgressBarValue)

	@script(description=_("Windows sleep mode"))
	def script_sleepMode(self, gesture):
		t = threading.Thread(target=winUser.windll.PowrProf.SetSuspendState, args=(False, False, False))
		t.start()

	@script(description=_("Reports last tooltip"))
	def script_reportLastTooltip(self, gesture):
		if not self._lastTooltip:
			ui.message(_("No tooltip"))
			return
		ui.message(self._lastTooltip)

	@script(description=_("Shows Speech Viewer"))
	def script_speechViewer(self, gesture):
		text = "\n".join(self._speechBuffer)
		TextWindow(text, _("Speech Viewer"), insertionPoint=-1)
