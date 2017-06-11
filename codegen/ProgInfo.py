################################################################################
# This file is part of ATOM
# Copyright (c) 2017 by Yifei Zheng
# Unauthorized copy, distribution and modification of this file is prohibited.
#
# This file contains structures to store data from source code, and useful
# processing routines for code generation.
################################################################################
import sys, os.path
from contextlib import contextmanager
from . import resolver
from . import manglers
from . import templating

sys.path.insert(0, os.path.abspath('..'))
from parser import expr
from collections import OrderedDict as odict, defaultdict
from itertools import chain, islice


def removeDup(seq):
    return list(odict.fromkeys(seq).keys())


def listVars(expr):
    if isinstance(expr, tuple):
        for i in expr[1]:
            yield from listVars(i)
    elif isinstance(expr, str):
        yield expr


class Variable:
    CTX_GLOBAL = 0
    CTX_MEM = 1
    CTX_TMP = 2

    def __init__(self, name, type, ctx, initializer=None):
        self.name = name
        self.type = type
        self.value = initializer
        self.ctx = ctx


class Op:
    def __init__(self, name, argc=1, writer=None):
        self.name = name
        self.argc = argc
        self.writer = writer

    def write(self, args):
        if self.writer:
            return self.writer(args)
        else:
            return '{}({})'.format(self.name, ', '.join(Rule.writeExpr(arg) for arg in args))

    def __repr__(self):
        return 'Op:' + self.name


@contextmanager
def tmp_var_writer(func):
    old_var_writer = Rule.VAR_WRITER
    Rule.VAR_WRITER = func
    yield
    Rule.VAR_WRITER = old_var_writer


def lambdify(expr):
    """
    Hollow out an expression by isolating the expression from environment,
    all arguments in the expression are preserved as is.
    """
    with tmp_var_writer(lambda x: manglers.split_mem(x)[1] if manglers.is_mem(x) else x):
        vars = list(listVars(expr))
        lambda_args = ', '.join('double ' + manglers.strip_mem(i) for i in vars)
        return vars, f'[]({lambda_args}){{ return {Rule.writeExpr(expr)}; }}'


def diff_writer(args):
    # TODO: This could be optimized, chain rule is generally slower because of the
    # extra fp multiplication. Use only when necessary (Requires hierachical change.)
    # FIXME: The separation of the two functions greatly hurts maintainability.
    if len(args) == 1:
        expr = args[0]
        wrt = 't'
    else:
        expr, wrt = args
    if wrt != 't':
        raise NotImplementedError()
    fnow = Rule.writeExpr(expr)
    fvars, flambda = lambdify(expr)
    # FIXME: round away from zero only, should be configurable
    calling_args = ', '.join(f'take_step({manglers.write_var(i)}, {manglers.write_var(i)})' for i in fvars)
    vnow = manglers.write_var(fvars.pop())
    vprev = f'last_data_.get(comb_.get(0)).{vnow}'
    return f'({flambda}({calling_args}) - {fnow}) * ({vnow} - {vprev}) / step'


def make_cs_diff_writer(NVar):  # cs stands for conditional substitution
    def _f(args):
        if len(args) == 1:
            expr = args[0]
            wrt = 't'
        else:
            expr, wrt = args
        if wrt != 't':
            raise NotImplementedError()
        fnow = Rule.writeExpr(expr)
        fvars, flambda = lambdify(expr)
        calling_args = ', '.join(
            f'take_step({manglers.write_var(i)}, {manglers.write_var(i)})' for i in fvars)
        var = fvars.pop()
        vnow = manglers.write_var(var)
        if manglers.strip_mem(var) == NVar.name:
            return f'({flambda}({calling_args}) - {fnow}) * {manglers.derivative(NVar)}'
        else:
            vprev = manglers.mem_prev(var, 2)
            return f'({flambda}({calling_args}) - {fnow}) * ({vnow} - {vprev}) / step'

    return _f


OP_TO_INST = {
    '+': Op('math::op::add', 2),
    '-': Op('math::op::sub', 2),
    '*': Op('math::op::mul', 2),
    '/': Op('math::op::div', 2),
    'pow': Op('std::pow', 2),
    'sin': Op('std::sin', 1),

    'sqrt': Op('math::sqrt', 1),
    'diff': Op('diff', 1, diff_writer),
}


@contextmanager
def tmp_op_writer(name, writer):
    old = OP_TO_INST[name].writer
    OP_TO_INST[name].writer = writer
    yield
    OP_TO_INST[name].writer = old


class SolvingStep:
    def __init__(self, content):
        self.content = content
        if isinstance(self.content[0], list):
            self.type = 0
        elif isinstance(self.content[0], int):
            self.type = 1
        else:
            self.type = 2

    def write(self, space, pack):
        STEP_START = ''
        STEP_END = ''
        cat = manglers.derivative
        prev = manglers.prev
        if self.type == 0:
            return STEP_START + f'math::solver::algebraic_sys({pack[self.content[0]]});\n' + STEP_END
        elif self.type == 1:
            rule_id = self.content[0]
            solveFor = self.content[1]
            with tmp_var_writer(lambda x: x if x == solveFor.name else manglers.write_var(x)):
                if self.content[1].order == 0:
                    name = solveFor.name
                    binding = f'double& {name} = srd_->get(comb_.get(0)).{name};\n'
                    binding += f'double {prev(name)} = last_data_.get(comb_.get(0)).{name};\n'
                    seed = prev(name)
                    return STEP_START + binding + f'{name} = math::solver::algebraic_single([&](double {name}){{\n' + \
                           pack[rule_id].write() + f'}}, {seed});\n' + STEP_END
                else:
                    name = cat(solveFor)
                    binding = f'double {name};\n'
                    seed = name
                    # chain rule must be considered if the unknown is a derivative.
                    # See make_cs_diff_writer for implementation
                    with tmp_op_writer('diff', make_cs_diff_writer(solveFor)):
                        return STEP_START + binding + f'{name} = math::solver::algebraic_single([&](double {name}){{\n' + \
                               pack[rule_id].write() + f'}}, {seed});\n' + STEP_END
        else:
            if self.content[1].order == 0:
                name = self.content[1].name
                binding = f'double& {name} = srd_->get(comb_.get(0)).{name};\n'
                binding += f'double {prev(name)} = last_data_.get(comb_.get(0)).{name};\n'
            else:
                name = cat(self.content[1].name)
                binding = f'double {cat(self.content[0])};\n'
            if self.content[1].order > self.content[0].order:
                return STEP_START + binding + f'{name} = ({name} - {prev(name)}) / step;\n' + STEP_END
            else:
                return STEP_START + binding + f'{name} = {prev(name)} + {cat(self.content[0])} * step;\n' + STEP_END

    def __str__(self):
        if self.type == 0:
            return f'ALG_M {self.content}'
        elif self.type == 1:
            return f'ALG_S {self.content[0]} -> {self.content[1]}'
        else:
            return f'DIFF_S {self.content[0]} -> {self.content[1]}'

    @property
    def updates(self):
        if self.type == 0:
            return self.content[1]
        else:
            return [self.content[1]]


class Rule:
    """Simple structure that stores a rule"""
    ITER = 1

    VAR_WRITER = manglers.write_var

    def __init__(self, content):
        self.content = expr.stringToExpr(content[0]), expr.stringToExpr(content[1])

    @staticmethod
    def writeExpr(expression: tuple):
        if isinstance(expression, str):
            return Rule.VAR_WRITER(expression)
        elif isinstance(expression, int):
            return str(expression)
        else:
            return OP_TO_INST[expression[0]].write(expression[1])

    def write(self):
        return 'return math::op::sub(' + self.writeExpr(self.content[0]) + ',\n' + self.writeExpr(
            self.content[1]) + ');\n'

    def __repr__(self):
        return f'Rule {self.content[0]} = {self.content[1]}'


class RulePack:
    """
    This is the class representing packed rules (RuleResolvingStruct) on
    highest level. That is, the pack is resolved further to actual steps,
    e.g. to solve as ODE or algebraic system, etc.
    """

    def __init__(self, content, solveFor):
        self.pack = content
        self.solveFor = solveFor
        self.steps = None

    def resolve(self, known):
        known = set(known).difference(i.name for i in self.solveFor)
        for i in self.pack:
            i.minus(known)

        self.steps = resolver.resolve(self.pack, self.solveFor)

    def __len__(self):
        return len(self.pack)

    def __iter__(self):
        yield from self.pack

    def __repr__(self):
        return '{\n\t' + '\n\t'.join(repr(i) for i in self.pack) + '\n} -> ' + repr(self.solveFor)


class CondRule:
    """
    None condition is used for else
    Empty content is used for assertion
    """

    def __init__(self, content):
        self.crpack = content
        self.vars = set()
        for cond, rulepack in self.crpack:
            for rule in rulepack:
                self.vars |= rule.vars

    COMP = ['==', '=', '!=', '<>', '<=', '<', '>=', '>']  # ORDER MATTERS, PREFER LONGER

    @staticmethod
    def writeCond(condition):
        for i in CondRule._infixCondToPrefix(condition):
            if isinstance(i, tuple):
                yield f'{i[0]}\n'
            else:
                comp = next(x for x in CondRule.COMP if x in i)
                lhs, rhs = i.split(comp)
                yield from Rule.writeExpr(expr.stringToExpr(lhs))
                yield from Rule.writeExpr(expr.stringToExpr(rhs))

    @staticmethod
    def _infixCondToPrefix(condition):
        if isinstance(condition, tuple):
            if len(condition) is 2:
                yield (condition[0], 1)  # protect operator with tuple
                yield condition[1]
            elif len(condition) is 3:
                yield (condition[1], 2)
                yield from CondRule._infixCondToPrefix(condition[0])
                yield from CondRule._infixCondToPrefix(condition[2])
        else:
            yield condition

    @staticmethod
    def writeRules(rulepack):
        for rule in rulepack:
            yield from rule.write()

    def write(self):
        yield 'if ('
        yield from self.writeCond(self.crpack[0])
        yield ') {\n'
        yield from self.writeRules(self.crpack[1])
        yield '}\n'
        if not self.crpack[-2]:
            for i, j in self.crpack[1:-1]:
                yield 'else if (\n'
                yield from self.writeCond(i)
                yield from self.writeRules(j)
            yield 'else {\n'
            yield from self.writeCond(self.crpack[-2])
            yield from self.writeRules(self.crpack[-1])
        else:
            for i, j in self.crpack[1:]:
                yield 'else if('
                yield from self.writeCond(i)
                yield from self.writeRules(j)

    def __repr__(self):
        return repr(self.crpack)


class RuleResolvingStruct:
    """Structure that holds necessary information to resolve rules to steps."""

    @staticmethod
    def findDerivatives(expression, DIFF=0):
        if isinstance(expression, tuple):
            if expression[0] == 'diff':
                DIFF += 1
            for i in expression[1]:
                yield from RuleResolvingStruct.findDerivatives(i, DIFF)
            if expression[0] == 'diff':
                DIFF -= 1
        elif isinstance(expression, str):
            expression = manglers.strip_mem(expression)
            yield resolver.cNVar(expression, DIFF)

    def __init__(self, idx, rule):
        self.idx = idx
        self.rule = rule
        findDerivatives = RuleResolvingStruct.findDerivatives
        self.diffs = set(chain(findDerivatives(rule.content[0]),
                               findDerivatives(rule.content[1])))
        self.vars = {i.name for i in self.diffs}

    def minus(self, set):
        self.vars = {i for i in self.vars if i not in set}
        self.diffs = {i for i in self.diffs if i.name not in set}

    def __repr__(self):
        return repr(self.rule)


class Space:
    def __init__(self):
        self.watched = odict()
        self.objects = odict()
        # FIXME: static initialization fiasco, shall be ordered instead
        self.globals = {
            "t": Variable('t', 'double', Variable.CTX_GLOBAL, 1),
            "step": Variable('step', 'double', Variable.CTX_GLOBAL, 1e-3)
        }
        self.vars = odict()
        self.funcs = {}  # reserved
        self.rules = []
        self.steps = None

    # FIXME: issue a warning instead of silent overwriting
    def addWatch(self, name, type='double'):
        self.watched[name] = Variable(name, type, Variable.CTX_MEM)

    def addObj(self, name, init=[]):
        self.objects[name] = Variable(name, 'Object', Variable.CTX_GLOBAL, init)

    def declTempVar(self, name, type):
        self.vars[name] = type

    def addRule(self, content):
        self.rules.append(Rule(content))

    def addCondRule(self, *args):
        self.rules.append(CondRule(args))

    def process(self):
        print("Processing...")
        known = list(chain(self.watched, self.globals))
        rrs = [RuleResolvingStruct(idx, i) for idx, i in enumerate(self.rules)]

        def find_candidate(known, all_vars):
            for i in known:
                for j in all_vars:
                    if j.name == i:
                        yield j

        def rotate(known, update):
            for i in update:
                try:
                    known.remove(i.name)
                    known.append(i.name)
                except ValueError:
                    pass

        # must loop by reference
        idx = 0
        while idx < len(rrs):
            Idx = idx
            eqn_count = 0
            needMore = True
            while needMore:
                Idx += 1
                eqn_count += 1
                # validate selection here
                all_vars = {var for i in rrs[idx:Idx] for var in i.diffs}
                update = {var for var in all_vars if var.name not in known}
                needMore = len(update) > eqn_count
            update.update(islice(find_candidate(known, all_vars), eqn_count - len(update)))
            rrs[idx:Idx] = [RulePack(rrs[idx:Idx], update)]
            rrs[idx].resolve(known)
            rotate(known, update)
            idx = Idx

        self.steps = removeDup(step for pack in rrs for step in pack.steps)
        self.steps = [SolvingStep(i) for i in self.steps]

        # finalize the steps, ensure update are propagated to watched values.
        updated_forms = defaultdict(set)
        for step in self.steps:
            for var in step.updates:
                updated_forms[var.name].add(var.order)
        update_not_fully_propagated = {}
        for var, forms in updated_forms.items():
            if min(forms) != 0 and var in self.watched:
                update_not_fully_propagated[var] = min(forms)
        # propagate the update to its watched base
        NVar = resolver.cNVar
        for var, min_idx in update_not_fully_propagated.items():
            self.steps.append(SolvingStep((NVar(var, min_idx), NVar(var, 0))))

    def write(self):
        # FIXME: This section should be generated
        def global_vars(var_vals, iterlen, object_len):
            for i in var_vals:
                yield f'{i.type} {i.name} = {i.value};'
            yield f'combinations<{iterlen}> comb_(0, {object_len});'

        print('Generating code...')
        gen = templating.template('codegen/template')
        while True:
            n = next(gen)
            if n is not None:
                yield n
            else:
                break
        yield gen.send(f'{var.type} {var.name};' for var in self.watched.values())
        while True:
            n = next(gen)
            if n is not None:
                yield n
            else:
                break
        yield gen.send(self.objects)
        while True:
            n = next(gen)
            if n is not None:
                yield n
            else:
                break
        yield gen.send(f'obj.{var.name}' for var in self.watched.values())
        while True:
            n = next(gen)
            if n is not None:
                yield n
            else:
                break
        yield gen.send(', '.join(str(i) for i in obj.value) for obj in self.objects.values())
        while True:
            n = next(gen)
            if n is not None:
                yield n
            else:
                break
        yield gen.send(global_vars(self.globals.values(), 1, len(self.objects)))
        while True:
            n = next(gen)
            if n is not None:
                yield n
            else:
                break
        yield gen.send([f'comb_.get(0) + 1 != {len(self.objects)}'])
        while True:
            n = next(gen)
            if n is not None:
                yield n
            else:
                break
        print('\n'.join(str(i) for i in self.steps))
        yield gen.send(i.write(self, self.rules) for i in self.steps)
        yield from gen

    def __repr__(self):
        return f'watched: {self.watched}\nvars: {self.globals}\nrules:\n' + '\n'.join(
            repr(i) for i in self.rules)
