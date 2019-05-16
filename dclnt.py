import ast
import os
import collections
from nltk import pos_tag
from abc import ABC, abstractmethod
from pygit2 import clone_repository
import json
import csv
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-w", "--wordtype", type=str, help="Find only selected word type. Args: 'VB' - verbs; 'NN' - noun")
parser.add_argument("-f", "--filter", type=str, help="Filter by expression type. "
                                                     "Args: 'Function' - filter function names;"
                                                     " 'Local' - filter local variables;"
                                                     " 'Name' - filter all words (default)")
parser.add_argument("-o", "--output", type=str, help="Type of output report. Args: 'console' - print result to console"
                                                     "(default); 'json' - put report to report.json;"
                                                     " 'csv' - put report to report.csv")


# Interface for Repository Manager
class _AbstractRepositoryCloneClass(ABC):

    @abstractmethod
    def clone_repository_by_url(self, url, path_to) -> None:
        pass


class GithubRepositoryClone(_AbstractRepositoryCloneClass):

    def clone_repository_by_url(self, url, path_to) -> None:
        clone_repository(url, path_to)


# Interface for Output Manager
class _AbstractOutputReportClass(ABC):

    @abstractmethod
    def output_report(self, report) -> None:
        pass


class ConsoleOutputReport(_AbstractOutputReportClass):

    def output_report(self, report) -> None:
        top_size = 200
        print('total %s words, %s unique' % (len(report), len(set(report))))
        for word, occurence in collections.Counter(report).most_common(top_size):
            print(word, occurence)


class JsonOutputReport(_AbstractOutputReportClass):

    def output_report(self, report) -> None:
        with open(os.path.join('.', 'report.json'), "w", encoding="utf-8") as file:
            json.dump(report, file)


class CsvOutputReport(_AbstractOutputReportClass):

    def output_report(self, report) -> None:
        with open(os.path.join('.', 'report.csv'), "w", encoding="utf-8", newline="") as file:
            csv_writer = csv.writer(file)
            csv_writer.writerows(report)


def _flat(_list):
    """ [(1,2), (3,4)] -> [1, 2, 3, 4]"""
    return sum([list(item) for item in _list], [])


def _is_magic_name(name):
    return name.startswith('__') and name.endswith('__')


def _get_tree(filename):
    with open(filename, 'r', encoding='utf-8') as attempt_handler:
        main_file_content = attempt_handler.read()
    try:
        tree = ast.parse(main_file_content)
    except SyntaxError as e:
        print(e)
        tree = None
    return tree


class Report:

    def __init__(self) -> None:
        self.words = []
        self._word_type = 'VB'
        self._top_size = None

    def _is_word_type(self, wrd):
        if not wrd:
            return False
        pos_info = pos_tag([wrd])
        return pos_info[0][1] == self._word_type

    def filter_word_type(self, word_type) -> None:
        self._word_type = word_type
        self.words = [word for word in self.words if self._is_word_type(word)]

    def set_top_size(self, top_size=10) -> None:
        self._top_size = top_size

    def set_word_list(self, _list):
        self.words = _list

    def create_report(self) -> list:
        if self._top_size:
            return collections.Counter(self.words).most_common(self._top_size)
        return [(word, '') for word in self.words]

    def split_all_words(self):

        def split_snake_case_name_to_words(fullname):
            return [name for name in fullname.split('_') if name]

        self.words = _flat([split_snake_case_name_to_words(word) for word in self.words])


# Abstract class for Analyze manager.
class _AbstractAnalyzerBuilder(ABC):

    def __init__(self, path) -> None:
        self.path = path
        self._exp = ['.py', ]

    def reset(self):
        self._report = Report()
        self._set_words_list()
        return self

    def set_path(self, path):
        self.path = path
        self.reset()
        return self

    def set_exp(self, _list):
        self._exp = _list
        self.reset()
        return self

    def _get_trees_in_path(self, exp):
        trees = []
        for dirname, dirs, files in os.walk(self.path, topdown=True):
            for file in files:
                if len(trees) == 100:
                    break
                filename = os.path.join(dirname, file)
                tree = _get_tree(filename) if file.endswith(exp) else None
                if tree:
                    trees.append(tree)
            else:
                continue
            break
        print('total %s files in %s' % (len(trees), self.path))
        print('trees generated')
        return trees

    def _set_words_list(self):
        trees = []
        for exp in self._exp:
            trees += self._get_trees_in_path(exp)
        self._report.set_word_list([word for word in self._get_words_from_tree(trees)
                                    if not _is_magic_name(word)])

    @property
    def report(self) -> Report:
        return self._report

    # Set "all result" as parameter of searching
    def all(self):
        self._report.set_top_size(None)
        return self

    # Set "most common result" as parameter of searching
    def top(self, top_size=10):
        self._report.set_top_size(top_size)
        return self

    # Filter result by verb wordtype.
    def filter_verb(self):
        self._report.filter_word_type('VB')
        return self

    # Filter result by noun wordtype.
    def filter_noun(self):
        self._report.filter_word_type('NN')
        return self

    # Split snake-case words.
    def split(self):
        self._report.split_all_words()
        return self

    @abstractmethod
    def _get_words_from_tree(self, trees) -> list:
        pass


class AnalyzerFunctionNames(_AbstractAnalyzerBuilder):

    def __init__(self, path='./'):
        super(AnalyzerFunctionNames, self).__init__(path)

    def _get_words_from_tree(self, trees) -> list:
        return _flat([[node.name.lower() for node in ast.walk(tree)
                       if isinstance(node, ast.FunctionDef)] for tree in trees])


class AnalyzerLocalVariables(_AbstractAnalyzerBuilder):
    def __init__(self, path='./'):
        super(AnalyzerLocalVariables, self).__init__(path)

    def _get_words_from_tree(self, trees) -> list:
        _list = [[node.targets[0] for node in ast.walk(tree) if isinstance(node, ast.Assign)] for tree in trees]
        return [word.id for word in _list[0] if getattr(word, 'id', None)]


class AnalyzerNames(_AbstractAnalyzerBuilder):
    def __init__(self, path='./'):
        super(AnalyzerNames, self).__init__(path)

    def _get_words_from_tree(self, trees) -> list:
        return _flat([[node.id for node in ast.walk(tree)
                       if isinstance(node, ast.Name)] for tree in trees])


if __name__ == '__main__':
    _outputs_dict = {'console': ConsoleOutputReport(),
                     'json': JsonOutputReport(),
                     'csv': CsvOutputReport()}

    _filters_dict = {'Function': AnalyzerFunctionNames(),
                     'Name': AnalyzerNames(),
                     'Local': AnalyzerLocalVariables()}

    args = parser.parse_args()
    filter = args.filter if args.filter else "Name"
    wordtype = args.wordtype
    output = args.output if args.output else "console"

    output_manager = _outputs_dict.get(output, ConsoleOutputReport)
    analyzer_manager = _filters_dict.get(filter, AnalyzerNames)
    repository_manager = GithubRepositoryClone()

    path_to = "./PyGithub"
    repository_url = "https://github.com/PyGithub/PyGithub"

    try:
        repository_manager.clone_repository_by_url(repository_url, path_to)
    except Exception as e:
        print(e)

    # Work with analyze manager
    analyzer_manager.set_path(path_to)

    if wordtype == 'VB':
        analyzer_manager.filter_verb()
    if wordtype == 'NN':
        analyzer_manager.filter_noun()

    analyzer_manager.top()

    # Get a report
    report = analyzer_manager.report.create_report()

    output_manager.output_report(report)
