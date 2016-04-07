"""Generic Math Processing
"""
import AhoCorasick
import math
from error import UnspecifiedVariable
# import abc
from itertools import product as cartesian
from collections import OrderedDict as odict
from string import Template
from operator import add, sub, mul, truediv, pow
from copy import deepcopy as copy


class plexpr:  # polish notation

    output = Template('${op}(${arg1}, ${arg2})')
    opfuncmap = {'+': add, '-': sub, '*': mul, '/': truediv, '^': pow,
                 'sin(': math.sin, 'cos(': math.cos, 'tan(': math.tan,
                 'sinh(': math.sinh, 'cosh(': math.cosh, 'tanh(': math.tanh,
                 'ln(': math.log, 'sqrt(': math.sqrt}

    def __init__(self, operator='+', arg1=0, arg2=0):

#        assert operator in plexpr.opfuncmap
        self.stroperator = operator
        self.priority = strexpr.priority.get(operator, 4)
        self.arg1 = arg1
        self.arg2 = arg2
        self.maxlevel = 1
        self.cursor = [2]  # cursor are initialized to point to arg2
        self.level = 1

    def get(self, cursor):
        result = self
        for i in cursor:
            result = result[i]
        return result

    def set(self, cursor, value):
        result = self
        if cursor:
            for i in cursor[:-1]:
                result = result[i]
            result[cursor[-1]] = value

    def isEnd(self):
        # recursive code need optimization
        result = self
        for i in self.cursor:
            result = result[i]
        if type(result) is plexpr:
            i = 2
            while result is not None:
                if type(result[i]) in {int, float, str}:
                    return True
                result = result[i]
            return False
        return True

    # the follwing four are shortcuts

    @property
    def operate(self):
        return plexpr.opfuncmap[self.stroperator]

    @property
    def req(self):
        result = self
        for i in range(self.level):
            result = result[2]
        return result

    @req.setter
    def req(self, value):
        result = self
        for i in range(self.level - 1):
            result = result[2]
        result[2] = value

    @property
    def reqexpr(self):
        result = self
        for i in range(self.level - 1):
            result = result[2]
        return result

    @reqexpr.setter
    def reqexpr(self, value):
        if self.level > 1:  # equivalent to >=2
            result = self
            for i in range(self.level - 2):
                result = result[2]
            result[2] = value
        elif self.level:
            self[0] = value[0]
            self[1] = value[1]
            self[2] = value[2]

    @property
    def reqexprop(self):  # return the immediate opearator of the req
        return self.reqexpr.stroperator

    def append(self, other, refop=None, bovrd=False, refcur=[], bsovrd=False):
#         print(self, other, self.cursor, refcur, sep='|')
        if other in strexpr.operators:  # token detected
            if bovrd:  # the first operator in a pair of brackets
                op1, op2 = 0, 1
            else:
                op1 = strexpr.priority[refop if refop else self.reqexprop]
                op2 = strexpr.priority[other]
            if op1 < op2:
                # the appending operator has higher priority
                assert self.isEnd()  # originally if
                # take the operator to the last appended operand
                self.req = plexpr(other, self.req, None)
                self.level += 1
            else:
                # the appeding operator has lower priotity
                if op2 < op1 and not bsovrd and self.level > len(refcur) + 1:
                    self.level -= 1
                assert self.isEnd()
                self.reqexpr = plexpr(other, copy(self.reqexpr), None)
        elif other in strexpr.tokens:  # separable tokens
            if other in strexpr.predeffunc:
                self.req = plexpr(other, self.req, None)
                self.level += 1
            # to eliminate brackets from numbers
        elif other[0].isalpha():
            self.req = other
        else:  # number detected
            self.req = int(other) if other.isnumeric() else float(other)

    @classmethod
    def simplify(cls, expr):
        for L in range(getlevel(expr), 0, -1):
            bottoms = findlevel(expr, L)
            bottoms = {_cur[:-1] for _cur in bottoms}
            for i in bottoms:
                subexpr = expr.get(i)
                typeset = {type(subexpr[1]), type(subexpr[2])}
                if typeset <= {int, float, str}:
                    if str not in typeset:
                        expr.set(i, subexpr())
                elif typeset <= {int, float, str, plexpr}:
                    if subexpr[1] is 0 or subexpr[2] is 0:
                        if subexpr[0] is '*':
                            expr.set(i, 0)
                        elif expr[0] is '+':
                            expr.set(i, subexpr[2] if subexpr[2] else subexpr[1])
                    elif subexpr[0] is '*' and (subexpr[1] is 1 or subexpr[2] is 1):
                            expr.set(i, subexpr[2] if subexpr[1] is 1 else subexpr[1])
        return expr

    def __iter__(self):
        for i in (1, 2):
            yield self[i]

    def __getitem__(self, index):
        if index is 2:
            return self.arg2
        elif index is 1:
            return self.arg1
        return self.stroperator

    def __setitem__(self, index, value):
        if index is 1:
            self.arg1 = value
        elif index is 2:
            self.arg2 = value
        else:
            self.stroperator = value

    def __repr__(self):
        return plexpr.output.substitute(op=self.stroperator.rstrip('('),
                                        arg1=self.arg1
                                        if self.arg1 is not None else '',
                                        arg2=self.arg2)

    def __call__(self, params={}):
        op1, op2 = self.arg1, self.arg2
        if type(op1) is plexpr:
            op1 = op1(params)
        elif type(op1) is str:
            try:
                op1 = params[op1]
            except KeyError:
                raise UnspecifiedVariable
        if type(op2) is plexpr:
            op2 = op2(params)
        elif type(op2) is str:
            try:
                op2 = params[op2]
            except KeyError:
                raise UnspecifiedVariable
        if op1 is not None:
            return self.operate(op1, op2)
        return self.operate(op2)


class strexpr:
    """
    A unique sturcture (to be written in C++) for math
    expression.
    Supports four elementary arithmetic operations and
    trigonometric, hyperbolic and logarithm functions.

    """
    predeffunc = {'sin', 'cos', 'tan',
                  'csc', 'sec', 'cot',
                  'sinh', 'cosh', 'tanh',
                  'ln', 'sqrt'}
    predeffunc = {_func + '(' for _func in predeffunc}
    Lbrackets = ['(', '[', '{']
    Rbrackets = [')', ']', '{']
    bracketsmap = dict(zip(Lbrackets, Rbrackets))
    operators = {'-', '+', '*', '/', '^', ' '}
    priority = dict(zip(['-', '+', '*', ' ', '/', '^'],
                        [1, 1, 2, 2, 2, 3]))
    tokens = set(operators) | predeffunc | set(Lbrackets) | set(Rbrackets)
    # PENDING = None

    ACtrie = AhoCorasick.ACProcessor(tokens, reduced=True)

    def __init__(self, _str, params=None):
        self.str = _str
        self.expr = None
        self.params = params
        self.requesting = []
        self.preprocess()
        self.final = plexpr('+', 0, None)  # error-prone
        self.process(self.cut())
        # should mark innermost level here
#         print(self.final)

    def preprocess(self):
        counter = strexpr.ACtrie(self.str)
        self.expr = strexpr.ACtrie.record

        if counter['('] + sum(counter[i] for i in strexpr.predeffunc) - strexpr.ACtrie.counter[')']:
            raise SyntaxError('Inconsistent brackets')

#         self.bs = self.matchbrackets()  # bracket structure

    def cut(self):
        tokens = [pos for key in self.expr.values() for pos in key]
        tokens.extend([pos + len(key) for key in self.expr for pos in self.expr[key]])
        tokens.sort()
        tokens = [0] + tokens + [len(self.str)]
        return [self.str[x:y] for x, y in zip(tokens, tokens[1:]) if y != x]

    def process(self, list):
        # generate token mapping
        _T = {i[0]: strexpr.priority[i[1]] for i in enumerate(list)
              if i[1] in strexpr.tokens}
        _O = odict(sorted(_T.items()))
        # process the raw mapping (naive method)
        _R = {}
        for i in reversed(_O):
            for j in reversed(_O):
                if j < i and _O[j] is _O[i]:
                    _R[i] = j
        # preprocess not well-behaved strings
        if list[0] in ('-', '+'):
            self.process(['0'] + self.cut())
        else:
        # main process goes here
            refop = []
            refcur = []
            opreq = False  # whether to request the first operator in brackets
            bsovrd = False
            for index, token in enumerate(list):
                if token in strexpr.operators:
                    if opreq:
                        opreq = 2
                if token is '(':
                    refop.append(self.final.reqexprop)
                    refcur.append(copy(self.final.cursor))
                    opreq = True
                elif token[-1] is '(':
                    # built-in func detected
                    # built-in func itself create a level in plexpr
                    # add another level in refcur
                    refop.append(self.final.reqexprop)
                    refcur.append(copy(self.final.cursor) + [2])
                    opreq = True

                # handle backspace exception

                def bsovrdperm(index):
                    for i in range(_O[index], index):
                        if i in _O and _T[i] < _T[index]:
                            return True
                    return False

                if index not in _R or bsovrdperm(index):
                    bsovrd = True
                self.final.append(token,
                                  refop.pop(-1) if refop else None,
                                  opreq,
                                  refcur[-1] if refcur else [],
                                  bsovrd)
                if bsovrd:
                    bsovrd = False
                if opreq is 2:
                    opreq = False
                if token in strexpr.operators:
                    refop.append(token)
                if token is ')':
                    self.final.cursor = refcur.pop(-1)
#             self.final = plexpr.simplify(self.final)

#     def matchbrackets(self):
#         Lindices, Rindices = list(self.expr['(']), list(self.expr[')'])
#         Lindices.sort()
#         Rindices.sort()
#         record = {i: 0 for i in Lindices}
#         for i in Lindices:
#             for j in enumerate(Rindices):
#                 if j[1] > i:
#                     if record[i]:
#                         record[i] = Rindices[record[i][0] + 1]
#                         record[i] = j
#                     else:
#                         record[i] = j
#                         break
#         record = {i: record[i][1] for i in record}
#         return record

    def __call__(self, valuedict={}):
        valuedict.update({'Pi': math.pi, 'e': math.e})
        return self.final(valuedict)

    def latex(self):
        return

    def __repr__(self):
        return str(self.final)


class relexpr():

    def __init__(self, _str, values={}):
        self.l, self.r = _str.split('=')
        self.l = strexpr(self.l, values)
        self.r = strexpr(self.r, values)
        self.values = values

    def __bool__(self):
        return self.l(self.values) == self.r(self.values)


def getlevel(expr: plexpr):
    string = repr(expr)  # reverse a plexpr to usual expression
    blevel = 0
    result = {}
    for index, i in enumerate(string):
        if i is '(':
            blevel += 1
        elif i is ')':
            blevel -= 1
        result[index] = blevel
    return max(result.values())


def findlevel(expr: plexpr, level: int):
    # enumerate!
    possibilities = cartesian((1, 2), repeat=level)
    for i in possibilities:
        try:
            expr.get(i)
            yield i
        except (TypeError, IndexError):  # indexerror for str
            pass

if __name__ == '__main__':
#     from math import isclose
    while True:
        try:
            expr = input('>>> ')
            se = strexpr(expr)
            plexpr.simplify(se.final)
#             print(isclose(se(), eval(expr.replace('^', '**'))), se.final)
#             print(se())
        except SyntaxError:
            print('Unbalanced Brackets')
#         except KeyboardInterrupt:
#             from sys import exit
#             exit(0)
