# -*- coding: utf-8 -*-

"""
ToDo: Document

Qudi is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Qudi is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Qudi. If not, see <http://www.gnu.org/licenses/>.

Copyright (c) the Qudi Developers. See the COPYRIGHT.txt file at the
top-level directory of this distribution and at <https://github.com/Ulm-IQO/qudi/>
"""

import copy
import inspect
import lmfit
from PySide2 import QtCore, QtWidgets
from qudi.core.util.mutex import Mutex
from qudi.core.util.units import create_formatted_output
from qudi.core import qudi_slot
from qudi.core import fit_models as __models


def __is_fit_model(cls):
    return inspect.isclass(cls) and issubclass(cls, __models.FitModelBase) and (
                cls is not __models.FitModelBase)


_fit_models = {name: cls for name, cls in inspect.getmembers(__models, __is_fit_model)}


class FitConfiguration:
    """
    """

    def __init__(self, name, model, estimator=None, custom_parameters=None):
        assert isinstance(name, str), 'FitConfiguration name must be str type.'
        assert name, 'FitConfiguration name must be non-empty string.'
        assert model in _fit_models, f'Invalid fit model name encountered: "{model}".'
        assert name != 'No Fit', '"No Fit" is a reserved name for fit configs. Choose another.'

        self._name = name
        self._model = model
        self._estimator = None
        self._custom_parameters = None
        self.estimator = estimator
        self.custom_parameters = custom_parameters

    @property
    def name(self):
        return self._name

    @property
    def model(self):
        return self._model

    @property
    def estimator(self):
        return self._estimator

    @estimator.setter
    def estimator(self, value):
        if value is not None:
            assert value in self.available_estimators, \
                f'Invalid fit model estimator encountered: "{value}"'
        self._estimator = value

    @property
    def available_estimators(self):
        return tuple(_fit_models[self._model]().estimators)

    @property
    def default_parameters(self):
        params = _fit_models[self._model]().make_params()
        return dict() if params is None else params

    @property
    def custom_parameters(self):
        return copy.deepcopy(self._custom_parameters) if self._custom_parameters is not None else None

    @custom_parameters.setter
    def custom_parameters(self, value):
        if value is not None:
            default_params = self.default_parameters
            invalid = set(value).difference(default_params)
            assert not invalid, f'Invalid model parameters encountered: {invalid}'
            assert all(isinstance(p, lmfit.Parameter) for p in
                       value.values()), 'Fit parameters must be of type <lmfit.Parameter>.'
        self._custom_parameters = copy.deepcopy(value) if value is not None else None


class FitConfigurationsModel(QtCore.QAbstractListModel):
    """
    """

    sigFitConfigurationsChanged = QtCore.Signal(tuple)

    def __init__(self, *args, configurations=None, **kwargs):
        assert (configurations is None) or all(isinstance(c, FitConfiguration) for c in configurations)
        super().__init__(*args, **kwargs)
        self._fit_configurations = list() if configurations is None else list(configurations)

    @property
    def model_names(self):
        return tuple(_fit_models)

    @property
    def model_estimators(self):
        return {name: tuple(model().estimators) for name, model in _fit_models.items()}

    @property
    def model_default_parameters(self):
        return {name: model().make_params() for name, model in _fit_models.items()}

    @property
    def configuration_names(self):
        return tuple(fc.name for fc in self._fit_configurations)

    @property
    def configurations(self):
        return self._fit_configurations.copy()

    @qudi_slot(str, str)
    def add_configuration(self, name, model):
        assert name not in self.configuration_names, f'Fit config "{name}" already defined.'
        assert name != 'No Fit', '"No Fit" is a reserved name for fit configs. Choose another.'
        config = FitConfiguration(name, model)
        new_row = len(self._fit_configurations)
        self.beginInsertRows(self.createIndex(new_row, 0), new_row, new_row)
        self._fit_configurations.append(config)
        self.endInsertRows()
        self.sigFitConfigurationsChanged.emit(self.configuration_names)

    @qudi_slot(str)
    def remove_configuration(self, name):
        try:
            row_index = self.configuration_names.index(name)
        except ValueError:
            return
        self.beginRemoveRows(self.createIndex(row_index, 0), row_index, row_index)
        self._fit_configurations.pop(row_index)
        self.endRemoveRows()
        self.sigFitConfigurationsChanged.emit(self.configuration_names)

    def get_configuration_by_name(self, name):
        try:
            row_index = self.configuration_names.index(name)
        except ValueError:
            raise ValueError(f'No fit configuration found with name "{name}".')
        return self._fit_configurations[row_index]

    def flags(self, index):
        if index.isValid():
            return QtCore.Qt.ItemIsEditable | QtCore.Qt.ItemIsEnabled

    def rowCount(self, parent=QtCore.QModelIndex()):
        return len(self._fit_configurations)

    def headerData(self, section, orientation, role=QtCore.Qt.DisplayRole):
        if role == QtCore.Qt.DisplayRole:
            if (orientation == QtCore.Qt.Horizontal) and (section == 0):
                return 'Fit Configurations'
            elif orientation == QtCore.Qt.Vertical:
                try:
                    return self.configuration_names[section]
                except IndexError:
                    pass
        return None

    def data(self, index=QtCore.QModelIndex(), role=QtCore.Qt.DisplayRole):
        if (role == QtCore.Qt.DisplayRole) and (index.isValid()):
            try:
                return self._fit_configurations[index.row()]
            except IndexError:
                pass
        return None

    def setData(self, index, value, role=QtCore.Qt.EditRole):
        if index.isValid():
            config = index.data(QtCore.Qt.DisplayRole)
            if config is None:
                return False
            new_params = value[1]
            params = {n: p for n, p in config.default_parameters.items() if n in new_params}
            for name, p in params.items():
                value_tuple = new_params[name]
                p.set(vary=value_tuple[0],
                      value=value_tuple[1],
                      min=value_tuple[2],
                      max=value_tuple[3])
            print('setData:', params)
            config.estimator = None if not value[0] else value[0]
            config.custom_parameters = None if not params else params
            self.dataChanged.emit(self.createIndex(index.row(), 0),
                                  self.createIndex(index.row(), 0))
            return True
        return False


class FitContainer(QtCore.QObject):
    """
    """
    sigFitConfigurationsChanged = QtCore.Signal(tuple)  # config_names
    sigLastFitResultChanged = QtCore.Signal(str, object)  # (fit_config name, lmfit.ModelResult)

    def __init__(self, *args, config_model, **kwargs):
        assert isinstance(config_model, FitConfigurationsModel)
        super().__init__(*args, **kwargs)
        self._access_lock = Mutex()
        self._configuration_model = config_model
        self._last_fit_result = None
        self._last_fit_config = 'No Fit'

        self._configuration_model.sigFitConfigurationsChanged.connect(
            self.sigFitConfigurationsChanged
        )

    @property
    def fit_configurations(self):
        return self._configuration_model.configurations

    @property
    def fit_configuration_names(self):
        return self._configuration_model.configuration_names

    @property
    def last_fit(self):
        with self._access_lock:
            return self._last_fit_config, self._last_fit_result

    @qudi_slot(str, object, object)
    def fit_data(self, fit_config, x, data):
        with self._access_lock:
            if fit_config:
                # Handle "No Fit" case
                if fit_config == 'No Fit':
                    self._last_fit_result = None
                    self._last_fit_config = 'No Fit'
                else:
                    config = self._configuration_model.get_configuration_by_name(fit_config)
                    model = config.model
                    estimator = config.estimator
                    add_parameters = config.custom_parameters
                    if estimator is None:
                        parameters = model.make_params()
                    else:
                        parameters = model.estimators[estimator](data, x)
                    if add_parameters is not None:
                        parameters.update(add_parameters)
                    self._last_fit_result = model.fit(data, parameters, x=x)
                    self._last_fit_config = fit_config
                self.sigLastFitResultChanged.emit(self._last_fit_config, self._last_fit_result)
                return self._last_fit_config, self._last_fit_result
            return '', None

    @staticmethod
    def formatted_result(fit_result, parameters_units=None):
        if fit_result is None:
            return ''
        if parameters_units is None:
            parameters_units = dict()
        parameters_to_format = dict()
        for name, param in fit_result.params.items():
            if not param.vary:
                continue
            parameters_to_format[name] = {'value': param.value,
                                          'error': param.stderr,
                                          'unit': parameters_units.get(name, '')}
        return create_formatted_output(parameters_to_format)