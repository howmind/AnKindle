# -*- coding: utf-8 -*-
# Created: 3/27/2018
# Project : AnKindle
import os
import re
import shutil
import sqlite3
from functools import partial
from operator import itemgetter

import anki
from anki import notes
from anki.lang import currentLang
from aqt import QAbstractTableModel, Qt, QAbstractItemView, isWin
from aqt import QDialog, QVBoxLayout, QFrame, \
    QPushButton, QSpacerItem, QLabel, QHBoxLayout, QSizePolicy, QGroupBox, QComboBox, QCheckBox, QTabWidget, QTableView, \
    QIcon
from aqt import mw, QSize
from aqt.importing import importFile
from aqt.progress import ProgressManager
from aqt.studydeck import StudyDeck
from aqt.utils import showInfo, getFile, showText, openLink, askUser
from .config import Config
from .const import ADDON_CD, __version__, ONLINE_DOC_URL, DEFAULT_TEMPLATE
from .db import VocabDB
from .kkLib import IS_PY3K
from .kkLib import WeChatButton, MoreAddonButton, VoteButton, _ImageButton, UpgradeButton, AddonUpdater, HLine, VLine
from .lang import _trans
from .libs import six
from .libs.mdict import mdict_query
from .libs.mdict import readmdict


class _HelpBtn(_ImageButton):
    def __init__(self, parent, help_text_or_file=None):
        if not help_text_or_file:
            if currentLang == 'zh_CN':
                help_text_or_file = os.path.join(os.path.dirname(__file__), "resource", "help_cn.html")
            else:
                help_text_or_file = os.path.join(os.path.dirname(__file__), "resource", "help_en.html")
        super(_HelpBtn, self).__init__(parent, os.path.join(os.path.dirname(__file__), "resource", "help.png"))
        self.setToolTip(_trans("Help"))
        self.help_text_or_file = help_text_or_file
        self.clicked.connect(self.on_clicked)

    def on_clicked(self):
        if os.path.isfile(self.help_text_or_file):
            if IS_PY3K:
                with open(self.help_text_or_file, encoding="utf-8") as f:
                    text = f.read()
            else:
                with open(self.help_text_or_file) as f:
                    text = f.read()
                    text = text.decode("utf-8")
        else:
            text = self.help_text_or_file
        dlg, box = showText(text
                            , self.parent(), "html", title=anki.lang._("Help"), run=False)
        online_template_doc = QPushButton(_trans("MORE_DOC"), dlg)
        online_template_doc.clicked.connect(partial(openLink, ONLINE_DOC_URL))
        dlg.layout().insertWidget(1, online_template_doc)
        dlg.exec_()


class _SharedFrame(QFrame):
    def __init__(self, parent, updater=None):
        super(_SharedFrame, self).__init__(parent)
        self.l_h_widgets = QHBoxLayout(self)
        wx = WeChatButton(self, os.path.join(os.path.dirname(__file__), "resource", "AnKindle.jpg"))
        wx.setIcon(os.path.join(os.path.dirname(__file__), "resource", "wechat.png"))
        wx.setObjectName("wx")
        self.l_h_widgets.addWidget(wx)
        vt = VoteButton(self, ADDON_CD)
        vt.setObjectName("vt")
        vt.setIcon(os.path.join(os.path.dirname(__file__), "resource", "upvote.png"))
        self.l_h_widgets.addWidget(vt)
        mr = MoreAddonButton(self)
        mr.setObjectName("mr")
        mr.setIcon(os.path.join(os.path.dirname(__file__), "resource", "more.png"))
        self.l_h_widgets.addWidget(mr)
        self.help_btn = _HelpBtn(self)
        self.l_h_widgets.addSpacerItem(QSpacerItem(10, 10, QSizePolicy.Expanding, QSizePolicy.Minimum, ))
        self.l_h_widgets.addWidget(self.help_btn)
        if updater:
            up_btn = UpgradeButton(self, updater)
            up_btn.setIcon(os.path.join(os.path.dirname(__file__), "resource", "update.png"))
            self.l_h_widgets.addWidget(up_btn)
            if isWin:
                up_btn.clicked.disconnect()
                up_btn.clicked.connect(
                    lambda: showText(_trans("WIN UPDATE") % ADDON_CD, parent, title=_trans("ANKINDLE")))


class Window(QDialog):
    # noinspection PyStatementEffect
    def __init__(self, parent, mod_list_func, deck_list_func):
        """

        :param parent:
        :param mod_list:
        :param deck_list:
        """

        super(Window, self).__init__(parent)
        self.setMinimumWidth(300)
        self.setStyleSheet("font-family: 'Microsoft YaHei UI', Consolas, serif;")
        self.mod_list_func = mod_list_func
        self.deck_list_func = deck_list_func

        # region init controls
        self.lb_db = QLabel(_trans("CANNOT FIND KINDLE VOLUME"), self)
        self.lb_db.setVisible(False)

        self.btn_select_db = _ImageButton(self, os.path.join(os.path.dirname(__file__), "resource", "kindle.png"))
        self.btn_select_db.clicked.connect(partial(self.on_select_kindle_db, True))
        self.btn_select_db.setToolTip(_trans("SELECT KINDLE DB"))
        self.btn_1select_model = QPushButton(_trans("SELECT MODEL"), self)
        self.btn_1select_model.clicked.connect(partial(self.on_select_model_clicked, None))
        self.btn_2select_deck = QPushButton(_trans("SELECT DECK"), self)
        self.btn_2select_deck.clicked.connect(partial(self.on_select_deck_clicked, None))

        self.btn_3select_mdx = QPushButton(_trans("SELECT MDX"), self)
        self.btn_3select_mdx.clicked.connect(partial(self.on_select_mdx, None))
        self.btn_3select_mdx.setEnabled(False)

        self.combo_lang = QComboBox(self)
        self.combo_lang.setMaximumWidth(100)
        self.combo_lang.setEnabled(False)

        self.updater = AddonUpdater(
            self, _trans("AnKindle"), ADDON_CD,
            "https://raw.githubusercontent.com/upday7/AnKindle/master/AnKindle/const.py",
            "",
            mw.pm.addonFolder(),
            __version__
        )

        # region layouts
        self.frm_widgets = _SharedFrame(self, self.updater)
        self.updater.start()

        frm_lists = QFrame(self)
        self.grp = QGroupBox(frm_lists)
        self.l_lists = QVBoxLayout(self.grp)

        l_grp_top = QHBoxLayout()
        self.l_lists.addWidget(self.lb_db, 0, Qt.AlignCenter)
        l_grp_top.addWidget(QLabel(_trans("Mandatory"), self), 0, Qt.AlignLeft)
        self.l_lists.addLayout(l_grp_top)

        l_language = QHBoxLayout()
        l_language.addWidget(self.btn_select_db)
        l_language.addWidget(VLine())
        l_language.addSpacerItem(QSpacerItem(1, 1, QSizePolicy.Minimum, QSizePolicy.Minimum))
        l_language.addWidget(QLabel(_trans("language"), self), 0, Qt.AlignLeft)
        l_language.addWidget(self.combo_lang)
        self.l_lists.addLayout(l_language)
        self.l_lists.addWidget(self.btn_1select_model)
        self.l_lists.addWidget(self.btn_2select_deck)

        l = QHBoxLayout()
        l.addWidget(self.btn_3select_mdx)

        self.l_lists.addWidget(HLine())
        self.l_lists.addWidget(QLabel(_trans("Optional"), self), 0, Qt.AlignLeft)
        self.l_lists.addLayout(l)

        self.btn_import = QPushButton(_trans("ONE CLICK IMPORT"), self, clicked=self.on_import)
        self.btn_import.setEnabled(False)

        self.btn_preview_words = QPushButton(self, clicked=self.on_preview_words)
        self.btn_preview_words.setToolTip(_trans("ANKINDLE WORDS PREVIEW"))
        self.btn_preview_words.setEnabled(False)
        self.btn_preview_words.setIcon(
            QIcon(os.path.join(os.path.dirname(__file__), "resource", "word_list.png"))
        )

        self.ck_import_new = QCheckBox(_trans("ONLY NEW WORDS"), self, clicked=self.on_ck_import_new)

        self.l = QVBoxLayout(self)
        self.l.addWidget(self.frm_widgets)
        self.l.addWidget(self.grp)
        l_import = QHBoxLayout()
        # self.ck_import_new.setFixedWidth(70)
        self.btn_preview_words.setFixedWidth(30)
        l_import.addWidget(self.ck_import_new)
        l_import.addWidget(self.btn_preview_words)
        l_import.addWidget(self.btn_import)
        self.l.addLayout(l_import)
        self.l.addSpacerItem(QSpacerItem(20, 10, QSizePolicy.Expanding, QSizePolicy.Minimum))

        # endregion

        # endregion

        self.model = None
        self.deck = None
        self.mdx = None
        self.builder = None
        self._preload_data = None
        self._lang_config_dict = {}
        self.db = None
        self.preview_words_win = WordsView(self)
        self.on_select_kindle_db(False)

        self.missed_css = set()

        # init actions
        self.btn_import.setDefault(True)
        try:
            self._validate_langs()
        except MemoryError:
            pass
        except:
            showInfo(_trans("ENSURE USB"), mw, type="warning", title=_trans("ANKINDLE"))
        # self.load_lang_default_config()

    def set_model_deck_button(self, on_combo_changed=False):
        model_id = self.lang_config.get("model_id")
        deck_id = self.lang_config.get("deck_id")
        if model_id and model_id in [str(m['id']) for m in self.mod_list] or on_combo_changed:
            self.on_select_model_clicked(model_id, on_combo_changed)
        if deck_id and deck_id in [str(m['id']) for m in self.deck_list] or on_combo_changed:
            self.on_select_deck_clicked(deck_id, on_combo_changed)

    def _validate_clicks(self):
        _ = all([self.model, self.deck, self.current_mdx_lang])
        self.btn_import.setEnabled(_)
        self.btn_preview_words.setEnabled(_)

    def _validate_langs(self):
        if self.word_langs:
            try:
                self.combo_lang.currentIndexChanged.disconnect(self.on_combo_lang_index_changed)
            except:
                pass
            self.combo_lang.clear()
            self.combo_lang.addItems(self.word_langs)
            self.combo_lang.setEnabled(True)
            self.btn_3select_mdx.setEnabled(True)

            if Config.last_used_lang:
                last_used_lang_index = self.combo_lang.findText(Config.last_used_lang)
                if last_used_lang_index == -1:
                    last_used_lang_index = 0
            else:
                last_used_lang_index = 0

            self.combo_lang.setCurrentIndex(last_used_lang_index)
            self.on_combo_lang_index_changed(last_used_lang_index)

            # warning ensure this is connected at last
            self.combo_lang.currentIndexChanged.connect(self.on_combo_lang_index_changed)

        self._validate_clicks()

    @property
    def current_mdx_lang(self):
        return self.combo_lang.currentText()

    @property
    def mod_list(self):
        return self.mod_list_func()

    @property
    def deck_list(self):
        return self.deck_list_func()

    @property
    def MDXFiles(self):
        from . import _try_ext_module
        if _try_ext_module():
            from .AnKindlePlus import GetMDXConfig
            return GetMDXConfig(self.current_mdx_lang)
        return ['', '', '', '', '', ]

    @property
    def MDXFilesFirstFile(self):
        for mdx_file in self.MDXFiles:
            if os.path.isfile(mdx_file):
                return mdx_file

    def on_ck_import_new(self, ):
        self.set_lang_config(import_new=self.ck_import_new.isChecked())

    def on_select_kindle_db(self, from_user_click):
        validated = False
        self.db = VocabDB(Config.last_used_db_path, from_user_click)
        if not self.db.is_available:
            self.lb_db.setVisible(True)
        else:
            self.lb_db.setVisible(False)
            if from_user_click:
                self._validate_langs()
            validated = True
        self.adjustSize()
        return validated

    def on_combo_lang_index_changed(self, index):
        Config.last_used_lang = self.combo_lang.currentText()
        self.mdx = self.lang_config.get("mdx_path")
        self.on_select_mdx(self.mdx, True)
        self.ck_import_new.setChecked(self.lang_config.get("import_new", True))
        self._validate_clicks()
        self.set_model_deck_button(True)

    def on_select_model_clicked(self, mid, ignore_selection=False):
        self.model = None
        if not mid:
            if not ignore_selection:
                study_deck_ret = self.select_model()
                self.model = mw.col.models.byName(study_deck_ret.name)
        else:
            self.model = mw.col.models.get(mid)

        if self.model:
            nm = self.model['name']
            self.btn_1select_model.setText(
                u'%s [%s]' % (_trans("NOTE TYPE"), nm))

            self.set_lang_config(model_id=str(self.model['id']) if self.model else u'')
        else:
            self.btn_1select_model.setText(_trans("SELECT MODEL"))
        self._validate_clicks()

    def select_model(self):
        if not self.mod_list:
            showText(_trans("USER DEFINED TEMPLATE ALERT"), self, "html", title=_trans("AnKindle"))
            importFile(mw, DEFAULT_TEMPLATE)

        edit = QPushButton(_trans("USE LATEST TEMPLATE"),
                           clicked=lambda x: importFile(mw, DEFAULT_TEMPLATE))

        ret = StudyDeck(mw, names=lambda: sorted([f['name'] for f in self.mod_list]),
                        accept=anki.lang._("Choose"), title=_trans("NOTE TYPE"),
                        parent=self, buttons=[edit], help='',
                        cancel=True)
        return ret

    def on_select_deck_clicked(self, did, ignore_selection=False):
        nm = None
        if did:
            nm = mw.col.decks.decks.get(did, {"name": ''})["name"]
        else:
            ret = None
            if not ignore_selection:
                ret = StudyDeck(
                    mw, accept=anki.lang._("Choose"),
                    title=anki.lang._("Choose Deck"),
                    cancel=True, parent=self)
            if ret:
                nm = ret.name
        if nm:
            self.deck = mw.col.decks.byName(nm)
            self.btn_2select_deck.setText(
                u'%s [%s]' % (_trans("DECK TYPE"), nm))

            self.set_lang_config(deck_id=str(self.deck['id']) if self.deck else u'')
        else:
            self.btn_2select_deck.setText(_trans("SELECT DECK"))

        self._validate_clicks()

    def on_select_mdx(self, file_path, ignore_selection=False):
        from . import _try_ext_module
        if _try_ext_module():
            if not ignore_selection:
                from .AnKindlePlus import MDXDialog
                dlg = MDXDialog(self, self.current_mdx_lang)
                dlg.exec_()
            mdx = self.MDXFilesFirstFile
            if mdx:
                self.btn_3select_mdx.setText(
                    u'[ %s ]' % (six.ensure_text(os.path.splitext(os.path.basename(mdx))[0])))
            else:
                self.btn_3select_mdx.setText(_trans("SELECT MDX"))
        else:
            self.on_select_mdx_legacy(file_path, ignore_selection)

    def on_select_mdx_legacy(self, file_path, ignore_selection=False):
        self.mdx = ''
        if file_path and os.path.isfile(file_path):
            self.mdx = file_path
        else:
            if not ignore_selection:
                self.mdx = getFile(self, _trans("MDX TYPE"), lambda x: x, ("MDict (*.MDX)"),
                                   os.path.join(os.path.dirname(__file__),
                                                u"resource") if not self.mdx else os.path.dirname(self.mdx)
                                   )

        if self.mdx and os.path.isfile(self.mdx):
            self.btn_3select_mdx.setText(
                u'%s [%s]' % (_trans("MDX TYPE"),
                              six.ensure_text(os.path.splitext(os.path.basename(self.mdx))[0])))
            self.set_lang_config(mdx_path=six.ensure_text(self.mdx) if self.mdx else u'')
        else:
            self.btn_3select_mdx.setText(_trans("SELECT MDX"))

    def get_html(self, word, builder):
        html = ''
        if not builder:
            return html

        try:
            result = builder.mdx_lookup(word)  # self.word: six.ensure_text
        except AttributeError:
            return ''

        if result:
            if result[0].upper().find(u"@@@LINK=") > -1:
                # redirect to a new word behind the equal symol.
                word = result[0][len(u"@@@LINK="):].strip()
                return self.get_html(word, builder)
            else:
                html = self.adapt_to_anki(result[0])
        return html

    def save_file(self, filepath_in_mdx, savepath=None):
        basename = os.path.basename(filepath_in_mdx.replace('\\', os.path.sep))
        if savepath is None:
            savepath = '_' + basename
        try:
            bytes_list = self.builder.mdd_lookup(filepath_in_mdx)
            if bytes_list and not os.path.exists(savepath):
                with open(savepath, 'wb') as f:
                    f.write(bytes_list[0])
                    return savepath
        except sqlite3.OperationalError as e:
            showInfo(str(e))

    def save_media_files(self, data):
        """
        get the necessary static files from local mdx dictionary
        ** kwargs: data = list
        """
        # diff = data.difference(self.media_cache['files'])
        # self.media_cache['files'].update(diff)
        lst, errors = list(), list()
        wild = [
            '*' + os.path.basename(each.replace('\\', os.path.sep)) for each in data]
        try:
            for each in wild:
                keys = self.builder.get_mdd_keys(each)
                if not keys:
                    errors.append(each)
                lst.extend(keys)
            for each in lst:
                self.save_file(each)
        except AttributeError:
            pass

        return errors

    def adapt_to_anki(self, html):
        """
        1. convert the media path to actual path in anki's collection media folder.
        2. remove the js codes (js inside will expires.)
        """
        # convert media path, save media files
        media_files_set = set()
        mcss = re.findall(r'href="(\S+?\.css)"', html)
        media_files_set.update(set(mcss))
        mjs = re.findall(r'src="([\w\./]\S+?\.js)"', html)
        media_files_set.update(set(mjs))
        msrc = re.findall(r'<img.*?src="([\w\./]\S+?)".*?>', html)
        media_files_set.update(set(msrc))
        msound = re.findall(r'href="sound:(.*?\.(?:mp3|wav))"', html)
        if 1:  # config.export_media
            media_files_set.update(set(msound))
        for each in media_files_set:
            html = html.replace(each, u'_' + each.split('/')[-1])
        # find sounds
        p = re.compile(
            r'<a[^>]+?href=\"(sound:_.*?\.(?:mp3|wav))\"[^>]*?>(.*?)</a>')
        html = p.sub(u"[\\1]\\2", html)
        self.save_media_files(media_files_set)
        for cssfile in mcss:
            cssfile = '_' + \
                      os.path.basename(cssfile.replace('\\', os.path.sep))
            # if not exists the css file, the user can place the file to media
            # folder first, and it will also execute the wrap process to generate
            # the desired file.
            if not os.path.exists(cssfile):
                self.missed_css.add(cssfile[1:])

        return html

    @property
    def lang_config(self):
        return Config.lang_config.get(self.current_mdx_lang, {"model_id": u"",
                                                              "deck_id": u"",
                                                              "import_new": True,
                                                              "mdx_path": u"", })

    def set_lang_config(self, **kwargs):
        orig_dict = self.lang_config
        args = kwargs.keys()
        if 'model_id' in args:
            orig_dict.update({'model_id': kwargs['model_id']})
        if 'deck_id' in args:
            orig_dict.update({'deck_id': kwargs['deck_id']})
        if 'mdx_path' in args:
            orig_dict.update({'mdx_path': kwargs['mdx_path']})
        if 'import_new' in args:
            orig_dict.update({'import_new': kwargs['import_new']})
        all_dicts = Config.lang_config
        all_dicts.update({self.current_mdx_lang: orig_dict})
        Config.lang_config = all_dicts

    @property
    def word_data(self):
        if not self._preload_data:
            self._preload_data = list(self.db.get_words(self.ck_import_new.isChecked()))
        return self._preload_data

    @property
    def word_langs(self):
        langs = set()
        for i, _ in enumerate(self.word_data):
            (id, word, stem, lang, added_tm, usage, title, authors, category) = _
            if lang:
                langs.add(lang.upper())
        return list(langs)

    def yield_one_word(self, filter_lang=''):
        self._preload_data = None
        # validate db still online
        if not self.on_select_kindle_db(False):
            showInfo(_trans("ENSURE USB"), mw, type="warning", title=_trans("ANKINDLE"))
            return
        progress = ProgressManager(mw)
        progress.start(immediate=True)
        words = self.word_data
        for i, _ in enumerate(words):
            progress.update(_trans("IMPORTING") + "\n{} / {}".format(i + 1, len(words)), i, True)
            (id, word, stem, lang, added_tm, usage, title, authors, category) = _
            if lang and (lang.upper() != (filter_lang if filter_lang else self.current_mdx_lang)):
                continue
            yield id, word, stem, lang, added_tm, usage, title, authors, category

        progress.finish()

    def on_import(self):
        from . import _try_ext_module

        total_new = 0
        total_dup = 0
        for i, _ in enumerate(self.yield_one_word()):
            (id, word, stem, lang, added_tm, usage, title, authors, category) = _
            # region save new cards
            try:
                note = notes.Note(mw.col, mw.col.models.models[str(self.model['id'])])
            except KeyError:
                continue
            note.model()['did'] = self.deck['id']

            qry_word = stem if stem else word if word else ''

            if _try_ext_module():
                mdx_files = self.MDXFiles
            else:
                mdx_files = [self.mdx, ]
            mdx_files = [m for m in mdx_files if os.path.isfile(m)]
            if not any(mdx_files):
                ret = askUser(
                    _trans("ALERT FOR MISSING MDX"), self, defaultno=False, title=_trans("ANKINDLE")
                )
                if not ret:
                    break
            dict_nm = ''
            dict_data = ''
            for mdx_file in mdx_files:
                self.builder = mdict_query.IndexBuilder(mdx_file)
                self.builder.get_header()
                self.builder.check_build()
                try:
                    mdx_dict = readmdict.MDX(mdx_file, only_header=True)
                    self.builder._encoding = mdx_dict._encoding
                except MemoryError:
                    showInfo(_trans("MDX MEMORY ERROR"), self, type="warning", title=_trans("ANKINDLE"))
                    continue
                except TypeError:
                    showInfo(_trans("MDX TYPE ERROR"), self, type="warning", title=_trans("ANKINDLE"))
                    continue
                dict_nm = os.path.splitext(os.path.basename(mdx_dict._fname))[0]

                self.missed_css = set()
                dict_data = self.get_html(qry_word, self.builder)
                # copy css files
                if dict_data:
                    mdx_dict_dir = os.path.split(mdx_file)[0]
                    include_mdx_extras = ['.CSS', '.JS']
                    for root, dirs, files in os.walk(mdx_dict_dir):
                        for _mfile in [css for css in files if os.path.splitext(css)
                                                               [1].strip().upper() in include_mdx_extras]:
                            _nfile = _mfile
                            if _mfile in self.missed_css:
                                _nfile = "_" + _mfile
                            shutil.copy(
                                os.path.join(root, _mfile),
                                _nfile
                            )
                    break

            _usage = self.adapt_to_anki(usage.replace(word, u"<b>%s</b>" % word)) if usage else ''
            try:
                _id_in_field = re.sub("[^0-9a-zA-Z]", "", qry_word + usage).strip().upper()
            except TypeError:
                return False

            def update_note(_note):
                _note.fields[_note._fieldOrd('id')] = _id_in_field if _id_in_field else ''
                _note.fields[_note._fieldOrd('word')] = word if word else ''
                _note.fields[_note._fieldOrd('stem')] = stem if stem else ''
                _note.fields[_note._fieldOrd('lang')] = lang if lang else ''
                _note.fields[_note._fieldOrd('creation_tm')] = added_tm if added_tm else ''
                _note.fields[_note._fieldOrd('usage')] = _usage if _usage else ''
                _note.fields[_note._fieldOrd('title')] = title if title else ''
                _note.fields[_note._fieldOrd('authors')] = authors if authors else ''
                _note.fields[_note._fieldOrd('mdx_dict')] = dict_data

                try:
                    _note.fields[_note._fieldOrd('mdx_name')] = dict_nm
                except KeyError:
                    pass
                return True

            if update_note(note):
                if note.dupeOrEmpty() != 2:
                    mw.col.addNote(note)
                    total_new += 1
                else:
                    total_dup += 1
                mw.col.autosave()
                # endregion

        mw.moveToState("deckBrowser")
        showText(_trans("CREATED AND DUPLICATES") % (total_new, total_dup), self)

    def on_preview_words(self):
        self.preview_words_win.lang = self.current_mdx_lang
        self.preview_words_win.refresh()
        self.preview_words_win.exec_()


class WordsView(QDialog):

    def __init__(self, parent):
        super(WordsView, self).__init__(parent)
        self.setWindowTitle(_trans("ANKINDLE WORDS PREVIEW"))
        self.setWindowIcon(QIcon(QIcon(os.path.join(os.path.dirname(__file__), "resource", "word_list.png"))))

        self.tabs = QTabWidget(self, currentChanged=self.on_current_tab_changed)
        self.learned_view = None
        self.new_view = None
        self.btn_refresh = QPushButton(_trans("REFRESH"), clicked=self.refresh)
        self.btn_refresh.setMinimumWidth(100)
        self.btn_mark_as_mature = QPushButton(_trans("MARK MATURE"), clicked=self.mark_mature)
        self.btn_mark_as_mature.setMinimumWidth(100)

        l = QVBoxLayout(self)
        l.addWidget(self.tabs)

        l_h = QHBoxLayout()
        l_h.addWidget(self.btn_refresh)
        l_h.addWidget(self.btn_mark_as_mature)
        l_h.addSpacerItem(QSpacerItem(100, 1, QSizePolicy.Expanding, QSizePolicy.Minimum))
        l.addLayout(l_h)

        self.lang = ''

    @property
    def word_data(self, ):
        if self.lang:
            new = list(self.parent().db.get_words(True))

            all = self.parent().db.get_words(False)

            old = [i for i in all if i not in new]
            return list(filter(lambda l: l[3].strip().upper() == self.lang.strip().upper(),
                               sorted(new + old, key=itemgetter(4), reverse=True)))
        else:
            return []

    def mark_mature(self):
        progress = ProgressManager(mw)
        progress.start(immediate=True)
        progress.update(_trans("Marking Words as Manure"))

        category = 100 if self.tabs.currentIndex() else 0
        if category:
            tableView = self.learned_view
        else:
            tableView = self.new_view

        for idx in tableView.selectionModel().selectedRows():
            kindle_word_id = tableView.model().word_data[idx.row()][0]
            self.parent().db.update_word_mature(kindle_word_id, 100 if not category else 0)

        progress.finish()
        self.refresh()

    def on_current_tab_changed(self, index):
        self.btn_mark_as_mature.setText(_trans("MARK MATURE") if not index else _trans("MARK NEW"))

    def refresh(self):
        _data_new = []
        _data_learned = []

        try:
            self.tabs.removeTab(0)
            self.tabs.removeTab(0)
        except:
            pass

        self.learned_view = None
        self.new_view = None

        self.new_model = WordsModel()
        self.learned_model = WordsModel()

        for _ in self.word_data:
            id, word, stem, lang, added_tm, usage, title, authors, category = _
            if category == 100:
                _data_learned.append(_)
            else:
                _data_new.append(_)

        if (not self.new_view):
            self.new_view = QTableView(self.tabs)
            self.new_model.set_data(_data_new)
            self.new_view.setModel(self.new_model)
            # self.new_view.setItemDelegate(StatusDelegate(self, self.new_model))
            self.tabs.addTab(self.new_view, _trans("NEW WORDS"))

        if not self.learned_view:
            self.learned_view = QTableView(self.tabs)
            self.learned_model.set_data(_data_learned)
            self.learned_view.setModel(self.learned_model)
            # self.learned_view.setItemDelegate(StatusDelegate(self, self.learned_model))
            self.tabs.addTab(self.learned_view, _trans("MATURE"))

        self.set_table_look()

    def set_table_look(self):
        for tableView in (self.new_view, self.learned_view):
            if not tableView:
                continue

            tableView.setMinimumSize(QSize(800, 400))
            tableView.setContextMenuPolicy(Qt.ActionsContextMenu)
            tableView.setFrameShape(QFrame.NoFrame)
            tableView.setFrameShadow(QFrame.Plain)
            tableView.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            tableView.setEditTriggers(QAbstractItemView.NoEditTriggers)
            tableView.setTabKeyNavigation(False)
            tableView.setAlternatingRowColors(True)
            tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
            tableView.horizontalHeader().setCascadingSectionResizes(False)
            tableView.horizontalHeader().setHighlightSections(False)
            tableView.horizontalHeader().setMinimumSectionSize(20)
            tableView.horizontalHeader().setSortIndicatorShown(True)

            tableView.horizontalHeader().hideSection(0)
            tableView.horizontalHeader().hideSection(3)
            tableView.horizontalHeader().hideSection(8)

            tableView.resizeColumnToContents(1)
            tableView.resizeColumnToContents(2)
            tableView.resizeColumnToContents(3)
            tableView.resizeColumnToContents(7)


# class StatusDelegate(QItemDelegate):
#
#     def __init__(self, browser, model):
#         QItemDelegate.__init__(self, browser)
#         self.model = model
#         self.browser = browser
#
#     def paint(self, painter, option, index):
#         if self.model.word_data[index.row()][0] in self.browser._to_be_matured:
#             brush = QBrush(QColor("#FFFFB2"))
#             painter.save()
#             fnt = QFont()
#             fnt.setBold(True)
#             painter.setFont(fnt)
#             painter.fillRect(option.rect, brush)
#             painter.restore()
#         return QItemDelegate.paint(self, painter, option, index)

# noinspection PyMethodOverriding
class WordsModel(QAbstractTableModel):

    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.sortKey = None
        self.activeCols = ['id', _trans('word'), _trans('stem'), 'lang', _trans('added_tm'),
                           _trans('usage'), _trans('title'), _trans('authors'), 'category']
        self.word_data = None

    def set_data(self, data):
        self.word_data = data

    def rowCount(self, index):
        """

        :type index: QModelIndex
        :return:
        """
        return len(self.word_data)

    def columnCount(self, index):
        """

        :type index: QModelIndex
        :return:
        """
        return len(self.activeCols)

    def data(self, index, role):
        """

        :type index: QModelIndex
        :return:
        """

        if not index.isValid():
            return
        elif role == Qt.TextAlignmentRole:
            align = Qt.AlignVCenter
            return align
        elif role == Qt.DisplayRole or role == Qt.EditRole or role == Qt.ToolTipRole:
            return self.columnData(index)
        else:
            return

    def headerData(self, section, orientation, role):
        if orientation == Qt.Vertical:
            return
        elif role == Qt.DisplayRole and section < len(self.activeCols):
            txt = self.columnType(section)
            return txt
        else:
            return

    def flags(self, index):
        return Qt.ItemFlag(Qt.ItemIsEnabled |
                           Qt.ItemIsSelectable)

    def columnType(self, column):
        return self.activeCols[column]

    def columnData(self, index):
        """

        :type index: QModelIndex
        :return:
        """
        row = index.row()
        col = index.column()
        return self.word_data[row][col]
