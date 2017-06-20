################################################################################
# This file is part of ATOM
# Copyright (c) 2017 by Yifei Zheng
# Unauthorized copy, distribution or modification of this file is prohibited.
#
# This module defines all runtime variable access patterns and recognizations,
# ensuring the uniformity throughout code generation. For demanglers, caller
# has to apply them in reverse order manglers has been applied, and carefully
# avoid demangling a not-mangled name.
################################################################################

import re


def prev(s):
    return s + '_prev'


def derivative(t):
    return f'{t.name}_{t.order}'


def fetch_mem(s):
    idx, attr = split_mem(s)
    return f'm_{idx}_{attr}'


def strip_mem(s):
    r = re.compile(r'\$.+\.')
    return r.sub('', s, count=1)


def split_mem(s):
    return s[1:].split('.', 1)


def is_mem(s):
    return re.match(r'\$.+\.', s.strip())


def mem_last(s):
    idx, attr = split_mem(s)
    return f'last_data_.get(comb_.get({idx})).{attr}'


def mem_cur(s):
    idx, attr = split_mem(s)
    return f'srd_->get(comb_.get({idx})).{attr}'


def mem_prev(s, steps):
    idx, attr = split_mem(s)
    return f'back_get(history, {steps}).get(comb_.get({idx})).{attr}'


def write_var(expression):
    try:
        return mem_last(expression)
    except ValueError:
        return expression