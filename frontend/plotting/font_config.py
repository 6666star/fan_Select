# -*- coding: utf-8 -*-
"""Matplotlib 中文字体配置"""
import os
import matplotlib.font_manager as fm
import matplotlib as mpl

_font_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'fonts', 'msyh.ttc')
if os.path.exists(_font_path):
    fm.fontManager.addfont(_font_path)
    _family = fm.FontProperties(fname=_font_path).get_name()
    mpl.rcParams['font.sans-serif'] = [_family] + mpl.rcParams['font.sans-serif']
    mpl.rcParams['axes.unicode_minus'] = False
