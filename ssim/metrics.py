from __future__ import annotations

import enum
import math
import hashlib


@enum.unique
class ImprovementType(int, enum.Enum):
    """An enumeration that is used to indicate the "sense" for a metric.

    This indicates whether a metric is better when minimized, maximized, etc.
    """
    Minimize = 0
    Maximize = 1
    SeekValue = 2

    @staticmethod
    def to_pretty_str(imp_type: ImprovementType):
        if imp_type == ImprovementType.Minimize:
            return "Minimize"

        if imp_type == ImprovementType.Maximize:
            return "Maximize"

        return "Seek Value"


    @staticmethod
    def parse(str: str):
        """A utility method to parse a string into a member of the
           ImprovementType enumeration.

        This will match the words minimize, min, maximize, max, seek value,
        seekvalue, seek, and the digits 0, 1, and 2.  The matching is case
        insensitive.

        Parameters
        ----------
        str : str
            The string to try and parse into a member of the ImprovementType
            enumeration.

        Returns
        -------
        ImprovementType:
            This returns the member of the enumeration that it matches to the
            supplied string.  If one cannot be matched, the return is None.
        """
        toParse = str.casefold()
        if toParse == "minimize":
            return ImprovementType.Minimize

        if toParse == "min":
            return ImprovementType.Minimize

        if toParse == "maximize":
            return ImprovementType.Maximize

        if toParse == "max":
            return ImprovementType.Maximize

        if toParse == "seek value":
            return ImprovementType.SeekValue

        if toParse == "seekvalue":
            return ImprovementType.SeekValue

        if toParse == "seek":
            return ImprovementType.SeekValue

        if toParse.isdigit():
            return ImprovementType(int(toParse))

        return None


def get_default_improvement_type(lower_limit: float, upper_limit: float, objective: float) -> ImprovementType:
    """A utility method to choose an appropriate improvement type based on the
       supplied limits and objective.

    This method can only make a minimization or maximization determination if one of
    the limits (upper or lower) is None.  If neither is None, the determination is seek value.

    If both limits are None, then no determination can be made.

    Parameters
    ----------
    lower_limit : float
        The lowest acceptable value for the metric.  Can be None.
    upper_limit : float
        The highest acceptable value for the metric.  Can be None.
    objective : float
        The target value which if obtained, provides full satisfaction. Cannot be None.

    Returns
    -------
    ImprovementType:
        This returns a value depending on the states of the supplied limits.
        If the lower_limit is None, then it is assumed that the desired sense is
        to minimize.  If the upper_limit is None, then the return is maximize.
        If neither is None, then the assumption is for seek value.  Finally, if
        both limits are none, a determination cannot be made and the return is None.
    """
    if lower_limit is None and upper_limit is None: return None
    if lower_limit is None: return ImprovementType.Minimize
    if upper_limit is None: return ImprovementType.Maximize
    return ImprovementType.SeekValue


def get_default_improvement_type(limit: float, objective: float) -> ImprovementType:
    """A utility method to choose an appropriate improvement type based on the
       supplied limit and objective.

    Parameters
    ----------
    limit : float
        The worst acceptable value for the metric.
    objective : float
        The target value which if obtained, provides full satisfaction.

    Returns
    -------
    ImprovementType:
        This returns ImprovementType.Minimize if the limit is less than the
        objective, ImprovementType.Maximize if the limit is greater than the
        objective, and None if the limit is equal to the objective.
    """
    if limit < objective:
        return ImprovementType.Maximize

    if limit > objective:
        return ImprovementType.Minimize

    return None


class Metric:
    """A class used to normalize metric values for subsequence combination and comparison.

    Parameters
    ----------
    lower_limit : float
        The lowest acceptable value for the metric if it is a maximization or seek value type.
        This value is not used for minimization type metrics.
    upper_limit : float
        The highest acceptable value for the metric if it is a minimization or seek value type.
        This value is not used for maximization type metrics.
    objective : float
        The target value which if obtained, provides full satisfaction.
    imp_type : ImprovementType
        The desired sense of the metric such as Minimize or Maximize.

        If this input is not provided, then a default is determined based on
        the limits and objective.
    a : float
        The parameter that controls the curvature of the normalization function
        beyond a limit (on the bad side of a limit).  It is recommended that
        you use the default value.
    b : float
        The parameter that controls the slope of the normalization curve at a
        limit.  It is recommended that you use the default value.
    c : float
        Sets the normalized value (y value) at a limit.  It is recommended
        that you use the default value.
    g : float
        The parameter that controls the curvature of the normalization function
        above the objective (on the good side of the objective).  It is
        recommended that you use the default value.
    """

    def __init__(
            self,
            lower_limit: float,
            upper_limit: float,
            objective: float,
            imp_type: ImprovementType = None,
            a: float = 5.0,
            b: float = 5.0,
            c: float = 0.0,
            g: float = 0.2
    ):
        self._lower_limit = lower_limit
        self._upper_limit = upper_limit
        self._objective = objective
        self._imp_type = imp_type

        if imp_type is None:
            self._imp_type = get_default_improvement_type(
                self._lower_limit, self._upper_limit, self._objective
            )

        self._a = a
        self._b = b
        self._c = c
        self._g = g
        self._validate_inputs()

    def __eq__(self, other):
        return self._lower_limit == other._lower_limit and \
            self._upper_limit == other._upper_limit and \
            self._objective == other._objective and \
            self._imp_type == other._imp_type and \
            self._a == other._a and \
            self._b == other._b and \
            self._c == other._c and \
            self._g == other._g

    def __hash__(self):        
        """Produces a hash value for this instance of a Metric.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpreter (non-salted).
        """
        m = hashlib.sha256()
        m.update(repr(self._lower_limit).encode())
        m.update(repr(self._upper_limit).encode())
        m.update(repr(self._objective).encode())
        m.update(repr(self._imp_type).encode())
        m.update(repr(self._a).encode())
        m.update(repr(self._b).encode())
        m.update(repr(self._c).encode())
        m.update(repr(self._g).encode())
        h = m.digest()
        return int.from_bytes(h, byteorder='big', signed=False)
    
    @property
    def lower_limit(self) -> float:
        """Allows access to the supplied lower limit value for this metric.

        Returns
        -------
        float:
            The lowest acceptable value for this metric.
        """
        return self._lower_limit

    @property
    def upper_limit(self) -> float:
        """Allows access to the supplied upper limit value for this metric.

        Returns
        -------
        float:
            The highest acceptable value for this metric.
        """
        return self._upper_limit

    @property
    def objective(self) -> float:
        """Allows access to the supplied objective value for this metric.

        Returns
        -------
        float:
            The value that provides full satisfaction for this metric.
        """
        return self._objective

    @property
    def improvement_type(self) -> ImprovementType:
        """Allows access to the supplied improvement type or "sense" for this
           metric.

        Returns
        -------
        ImprovementType:
            The enumeration member that indicates the sense of this metric
            (minimize, maximize, etc.)..
        """
        return self._imp_type

    @staticmethod
    def read_toml(tomlData) -> Metric:
        """Reads the properties of a metric class instance from a TOML
           formatted dictionary and creates and returns a new Metric instance.
        
        Parameters
        ----------
        tomlData: dict
            The dictionary that contains the metric properties from which to
            create a new metric instance.  The minimum set of keys that must
            be present are "lower_limit", "upper_limit", "objective", and "sense".
            "sense" must point to something that can be parsed to an ImprovementType
            enumeration value.

        Returns
        -------
        Metric:
            A newly created metric made using the properties in the supplied
            TOML dictionary.
        """
        lower_limit = tomlData.get("lower_limit")
        upper_limit = tomlData.get("upper_limit")
        objective = tomlData.get("objective")
        impType = tomlData.get("sense")
        if impType: impType = ImprovementType.parse(impType)
        return Metric(lower_limit, upper_limit, objective, impType)

    def write_toml(self, category, key) -> str:
        """Writes the properties of this class instance to a string in TOML format.
        
        Parameters
        ----------
        category : str
            The category under which this metric is being stored if any.  This
            would be passed in from a metric owner and is optional.  If it is
            None, then the category tag will not be written.
        key : str
            The key to which this metric is mapped by a metric owner.  This
            value is optional.  If the key is None, then no key tag will be
            written.

        Returns
        -------
        str:
            A TOML formatted string with the properties of this instance.
        """
        # ret = f"\n\n[metrics.{category}.{key}]\n"
        ret = "{" + f"name=\"{key}\", "
        if self._lower_limit is not None:
            ret += f"lower_limit = {str(self._lower_limit)}, "

        if self._upper_limit is not None:
            ret += f"upper_limit = {str(self._upper_limit)}, "

        if self._objective is not None:
            ret += f"objective = {str(self._objective)}, "

        if self._imp_type is not None:
            ret += f"sense = \"{str(self._imp_type.name)}\""

        return ret + "}"

    def to_dict(self, key: str) -> dict:
        """Return a dictionary representation of this metric.

        Parameters
        ----------
        key : str
            The key to which this metric is mapped by a metric owner.

        Returns
        -------
        dict
            A dictionary representation of the metric. Include keys "name",
            "objective", "upper_limit", and "lower_limit".
        """
        return {
            "name": key,
            "lower_limit": self._lower_limit,
            "upper_limit": self._upper_limit,
            "objective": self._objective,
            "sense": ImprovementType.to_pretty_str(self._imp_type)
        }

    def normalize(self, value: float) -> float:
        """Convert a raw metric value into a normalized fitness value.

        Parameters
        ----------
        value : float
            The raw metric value in natural units.

        Returns
        -------
        float:
            A normalized value based on the supplied raw value, this metrics
            limit values, the objective, and the other curve parameters of this metric.
        """
        if self._imp_type == ImprovementType.Minimize:
            return self._normalize_for_minimization(value)

        if self._imp_type == ImprovementType.Maximize:
            return self._normalize_for_maximization(value)

        return self._normalize_for_seek_value(value)

    def _normalize_for_minimization(self, value: float) -> float:
        """Convert a raw metric value into a normalized fitness value for a
           minimization metric.

        Parameters
        ----------
        value : float
            The raw metric value in natural units.

        Returns
        -------
        float:
            A normalized value based on the supplied raw value, this metrics
            lower limit and objective, and the other curve parameters of this metric.
            this does calculations for a metric meant for minimization.
        """
        return self.__do_max_norm__(-value, -self._upper_limit, -self._objective)

    def _normalize_for_maximization(self, value: float) -> float:
        """Convert a raw metric value into a normalized fitness value for a
           maximization metric.

        Parameters
        ----------
        value : float
            The raw metric value in natural units.

        Returns
        -------
        float:
            A normalized value based on the supplied raw value, this metrics
            upper limit and objective, and the other curve parameters of this metric.
            this does calculations for a metric meant for maximization.
        """
        return self.__do_max_norm__(value, self._lower_limit, self._objective)

    def _normalize_for_seek_value(self, value: float) -> float:
        """Convert a raw metric value into a normalized fitness value for a
           seek value metric.

        Parameters
        ----------
        value : float
            The raw metric value in natural units.

        Returns
        -------
        float:
            A normalized value based on the supplied raw value, this metrics
            limits and objective, and the other curve parameters of this metric.
            This does calculations for a metric meant for seek value.
        """
        if value < self._objective:
            return self._normalize_for_maximization(value)

        return self._normalize_for_minimization(value)

    def _violated(self, norm_val: float) -> float:
        """Calculates the normalized value of a pre-normalized metric value
           that falls in the region of the space beyond (worse than) a limit.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that
            is to be normalized.  It must have been a metric value in the
            violated region (worse than a limit).

        Returns
        -------
        float:
            A normalized value based on the supplied pre-normalized value
            and the other curve parameters of this metric.
        """
        return -(self._a * norm_val * norm_val) / 2.0 + \
            self._b * norm_val + self._c

    def _feasible(self, norm_val: float) -> float:
        """Calculates the normalized value of a pre-normalized metric value
           that falls in one of the regions between a limit and the objective.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that
            is to be normalized.  It must have been a metric value in one of the
            regions between a limit and the objective.

        Returns
        -------
        float:
            A normalized value based on the supplied pre-normalized value, this
            metrics limits and objective, and the other curve parameters of this
            metric.
        """
        d = self._d()
        return d * math.sqrt(norm_val + self._f(d)) + self._c - self._psi(d)

    def _super_optimal(self, norm_val: float) -> float:
        """Calculates the normalized value of a pre-normalized metric value
           that falls in the region beyond (better than) the objective.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that
            is to be normalized.  It must have been a metric value in the
            region beyond (better than) the objective.

        Returns
        -------
        float:
            A normalized value based on the supplied pre-normalized value and the
            other curve parameters of this metric.
        """
        h = self._h(self._d())
        return self._g * math.sqrt(norm_val + h - 1.0) - self._phi(h) + 1.0

    def _d(self) -> float:
        '''An intermediate value used in several places during normalization.

        Returns
        -------
        float:
            The "d" value for this metric.
        '''
        x = 1.0 - 2.0 * self._c + self._c * self._c
        y = self._c + self._b - 1.0
        return math.sqrt(self._b * x / y)

    def _f(self, d: float) -> float:
        '''An intermediate value used in several places during normalization.

        Parameters
        ----------
        d: float
            The "d" value for this metric, typically computed using the
            self._d method.

        Returns
        -------
        float:
            The "f" value for this metric.
        '''
        val = d / (2.0 * self._b)
        return val * val

    def _psi(self, d: float) -> float:
        '''An intermediate value used in several places during normalization.

        Parameters
        ----------
        d: float
            The "d" value for this metric, typically computed using the
            self._d method.

        Returns
        -------
        float:
            The "psi" value for this metric.
        '''
        return (d * d) / (2.0 * self._b)

    def _h(self, d: float) -> float:
        '''An intermediate value used in several places during normalization.

        Parameters
        ----------
        d: float
            The "d" value for this metric, typically computed using the
            self._d method.

        Returns
        -------
        float:
            The "h" value for this metric.
        '''
        return (self._g * self._g * (self._f(d) + 1.0)) / (d * d)

    def _phi(self, h: float) -> float:
        '''An intermediate value used in several places during normalization.

        Parameters
        ----------
        d: float
            The "h" value for this metric, typically computed using the
            self._h method.

        Returns
        -------
        float:
            The "phi" value for this metric.
        '''
        return self._g * math.sqrt(h)

    @staticmethod
    def _do_pre_normalization(
        raw_value: float, limit: float, objective: float
        ) -> float:
        """Calculates the pre-normalized equivalent of the supplied raw value
           for the given limit and objective.

        This is computed as the (raw_value - limit) / (objective - limit). 
        Without this pre-normalization, the distance between the limit and
        objective of two different metrics may skew the pressure of a comparer
        toward or away from one or the other inappropriately.

        Parameters
        ----------
        raw_value : float
            The raw value of a metric that is in the process of being normalized.
        limit : float
            The worst acceptable value for the metric.
        objective : float
            The target value which if obtained, provides full satisfaction.

        Returns
        -------
        float:
            The result of pre-normalizing the raw_value.
        """
        return (raw_value - limit) / (objective - limit)

    def __do_max_norm__(
        self, value: float, limit: float, objective: float
        ) -> float:
        """Calculates the normalized equivalent of the supplied raw value for
           the supplied limit and objective assuming maximization.

        This treats the normalization as maximization but is used for all
        current forms of normalization.  For example, minimization is done by
        negating the limit and objective prior to sending them into this
        method.

        Parameters
        ----------
        value : float
            The raw value of a metric that is to be normalized.
        limit : float
            The worst acceptable value for the metric.
        objective : float
            The target value which if obtained, provides full satisfaction.

        Returns
        -------
        float:
            The result of normalizing the value for maximization.
        """
        resp_norm = Metric._do_pre_normalization(value, limit, objective)

        if value < limit:
            return self._violated(resp_norm)
        if value < objective:
            return self._feasible(resp_norm)
        return self._super_optimal(resp_norm)

    def _validate_inputs(self, do_assert: bool = True) -> str:
        """Tests the validity/usability of the values stored in this metric.

        This uses the static validate_metric_values method.  See it for details.
        
        Parameters
        ----------
        do_assert : bool
            A flag that indicates whether this method should throw an exception
            (true) or return an error message as a string (false).

        Returns
        -------
        str:
            This method either throws an exception or returns a string
            depending on the value of do_assert.  Either way, the message is
            determined using the conditions laid out in the description.  If there
            are no problems, then the return is None.
            
        Raises
        ------
        AssertionError:
            If any of the conditions listed in the description are present and
            the do_assert parameter is set to true.
        """
        Metric.validate_metric_values(
            self._lower_limit, self._upper_limit, self._objective, self._imp_type, do_assert
        )

    @staticmethod
    def validate_metric_values(
        lower_limit: float, upper_limit: float, objective: float, imp_type: ImprovementType,
        do_assert: bool = False
        ) -> str:
        """Tests the validity/usability of the metric values provided.

        This will either return an error string or throw an exception with an
        error message.  Which it does will be determined by the do_assert
        parameter.  The requirements are that:
            The objective cannot be None.
            The improvement type cannot be None.
            if the imp_type is minimize, the upper_limit must not be None.
            If the imp_type is maximize, the lower_limit must not be None.
            If the imp_type is seek value, then neither limit can be None.
            If there is a lower_limit, then it must be less than the objective.
            If there is an upper_limit, then it must be greater than the objective.

        Neither limit can be equal to the objective.

        Parameters
        ----------
        lower_limit : float
            The lowest acceptable value for a metric.
        upper_limit : float
            The highest acceptable value for a metric.
        objective : float
            The target value which if obtained, provides full satisfaction.
        imp_type : ImprovementType
            The desired sense of a metric such as Minimize or Maximize.
        do_assert : bool
            A flag that indicates whether this method should throw an exception
            (true) or return an error message as a string (false).

        Returns
        -------
        str:
            This method either throws an exception or returns a string
            depending on the value of do_assert.  Either way, the message is
            determined using the conditions laid out in the description.
            
        Raises
        ------
        AssertionError:
            If any of the conditions listed in the description are present and
            the do_assert parameter is set to true.
        """
        try:
            assert objective != None, \
                "A value must be provided for the objective."

            assert imp_type != None, \
                "A value must be provided for the sense."

            if imp_type == ImprovementType.Minimize:
                assert upper_limit is not None, \
                    "The upper limit cannot be None for a minimization metric"
                assert upper_limit > objective, \
                    "The upper limit must be greater than the objective"

            elif imp_type == ImprovementType.Maximize:
                assert lower_limit is not None, \
                    "The lower limit cannot be None for a maximization metric"
                assert lower_limit < objective, \
                    "The lower limit must be less than the objective"

            else:  # elif imp_type == ImprovementType.SeekValue:
                assert upper_limit is not None, \
                    "The upper limit cannot be None for a seek value metric"
                assert upper_limit > objective, \
                    "The upper limit must be greater than the objective"
                assert lower_limit is not None, \
                    "The lower limit cannot be None for a seek value metric"
                assert lower_limit < objective, \
                    "The lower limit must be less than the objective"

            return None
        except AssertionError as err:
            if do_assert:
                raise

            return str(err)


class MetricAccumulator:
    """A class used to accumulate normalized metric values over time.

    This class is rarely used directly.  Its primary purpose is as a base
    class providing functionality to for example, the MetricTimeAccumulator.
    
    Parameters
    ----------
    m : Metric
        The metric whose value will be accumulated over time.
    """

    def __init__(self, m: Metric = None):
        self._metric = m
        self._accumulated = 0.0
        self._total_time = 0.0

    def __eq__(self, other):
        return self._metric == other._metric

    def __hash__(self):
        """Produces a hash value for this instance of a MetricAccumulator.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpreter (non-salted).
        """
        return hash(self._metric)

    def accumulate(self, value: float, d_time: float) -> float:
        """Adds in normalized value weighted by the amount of time provided.

        Parameters
        ----------
        value : float
            The raw metric value to be normalized and accumulated into this
            accumulator. This value will be normalized by the contained Metric.
        d_time: float
            The amount of time over which the provided value applies.  This is
            used as a weighting factor in the accumulation.
            
        Returns
        -------
        float:
            The result of normalizing the supplied value parameter.
        """
        if d_time == 0.0: return 0.0
        met_val = self._metric.normalize(value)
        self._total_time += d_time
        self._accumulated += d_time * met_val
        return met_val

    def to_dict(self, key: str) -> dict:
        """Return a dictionary representation of the metric being accumulated.
        
        Parameters
        ----------

        key : str
            The key to which this metric accumulator is mapped by a metric
            owner.

        Returns
        -------

        dict
            A dictionary representation of the metric managed by this accumulator.
        """
        return self._metric.to_dict(key)

    def write_toml(self, category: str, key: str) -> str:
        """Writes the properties of this class instance to a string in TOML
           format.
        
        Parameters
        ----------
        category : str
            The category under which this metric accumulator is being stored if
            any. This would be passed in from a metric owner and is optional. 
            If it is None, then the category tag will not be written.
        key : str
            The key to which this metric accumulator is mapped by a metric
            owner. This value is optional.  If the key is None, then no key tag
            will be written.

        Returns
        -------
        str:
            A TOML formatted string with the properties of this instance.
        """
        return self._metric.write_toml(category, key)

    @staticmethod
    def read_toml(tomlData: dict) -> MetricAccumulator:
        """Reads the properties of a metric accumulator class instance from a
           TOML formatted dictionary and creates and returns a new
           MetricAccumulator instance.
        
        Parameters
        ----------
        tomlData: dict
            The dictionary that contains the metric accumulator properties from
            which to create a new instance.  The minimum set of keys that must
            be present are only those associated with a Metric.

        Returns
        -------
        MetricAccumulator:
            A newly created metric accumulator made using the properties in the
            supplied TOML dictionary.
        """
        m = Metric.read_toml(tomlData)
        return MetricAccumulator(m)

    @property
    def accumulated_value(self) -> float:
        """Allows access to the current accumulation value.  This is the time
           weighted sum of normalized values.

        Returns
        -------
        float:
            The current time weighted sum of normalized values.
        """
        return self._accumulated

    @property
    def total_time(self) -> float:
        """Allows access to the current sum of all accumulated time.

        Returns
        -------
        float:
            The current sum of all accumulated time.
        """
        return self._total_time

    @property
    def denormalized_value(self) -> float:
        """Allows access to the current total accumulation divided by the total
           time.

        Returns
        -------
        float:
            The current total accumulation over the total time accumulated so far.
        """
        return self._accumulated / self._total_time

    @property
    def metric(self) -> Metric:
        """Allows access to the Metric being used by this accumulation.

        Returns
        -------
        Metric
            The metric that underlies this accumulator.
        """
        return self._metric


class MetricTimeAccumulator(MetricAccumulator):
    """A class used to accumulate a normalize metric value over time.

    This class differs from (specializes) the MetricAccumulator class in that
    it always keeps track of the current time as the last time a call was made
    to accumulate.  It then provides the delta T to the base and updates its
    current time.
    
    Parameters
    ----------
    m : Metric
        The metric whose value will be accumulated over time.
    init_time : float
        The time to be the initial "current time" for this accumulator.
        The default is 0.
    """

    def __init__(self, m: Metric, init_time: float = 0.0):
        MetricAccumulator.__init__(self, m)
        self._curr_time = init_time

    def __eq__(self, other):
        return self._metric == other._metric

    def __hash__(self):
        """Produces a hash value for this instance of a MetricTimeAccumulator.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpreter (non-salted).
        """
        return hash(self._metric)

    @staticmethod
    def read_toml(tomlData) -> MetricTimeAccumulator:
        """Reads the properties of a metric time accumulator class instance
           from a TOML formatted dictionary and creates and returns a new
           MetricTimeAccumulator instance.
        
        Parameters
        ----------
        tomlData
            The dictionary that contains the metric time accumulator properties
            from which to create a new instance.  The minimum set of keys that
            must be present are only those associated with a Metric.

        Returns
        -------
        MetricTimeAccumulator:
            A newly created metric time accumulator made using the properties
            in the supplied TOML dictionary.
        """
        m = Metric.read_toml(tomlData)
        return MetricTimeAccumulator(m)

    def accumulate(self, value: float, curr_time: float) -> float:
        """Adds in normalized value weighted by the difference between the last
           time this method was called and the time provided.

        Parameters
        ----------
        value : float
            The raw metric value to be normalized and accumulated into this
            accumulator. This value will be normalized by the contained Metric.
        curr_time: float
            The simulation time of this call to be used along with the last
            time this method was called for accumulation purposes.
            
        Returns
        -------
        float:
            The result of normalizing the supplied value parameter.
        """
        assert curr_time >= self._curr_time, \
            "current time provided to accumulate function must be greater " + \
            "than or equal to any prior time provided."
        if curr_time == self._curr_time: return 0.0
        val = MetricAccumulator.accumulate(
            self, value, curr_time - self._curr_time
        )
        self._curr_time = curr_time
        return val


class MetricManager:
    """A class used to manage a set of metric accumulators keyed on names."""

    def __init__(self):
        self._all_metrics = {}

    def __eq__(self, other):
        """Checks to see if this manager is functionally equivalent to another.

        Functionally equivalent means that for the purpose of solving, this manager will
        be effectively equivalent. An example of functionally equivalent but not strictly
        equivalent would be if the metrics are the same but not in the same order in the
        dictionary.

        Parameters
        ----------
        other:
            The other MetricManager to compare to this for functional equivalence.

        Return
        ------
        bool:
            True if the other is functionally equivalent to this and False otherwise.
        """
        if len(self._all_metrics) != len(other._all_metrics): return False

        for mk, ma in self._all_metrics.items():
            if mk not in other._all_metrics: return False
            if ma != other._all_metrics[mk]: return False

        return True

    def __hash__(self):
        """Produces a hash value for this instance of a MetricManager.

        This only takes into account the core properties of the object, not
        values that store current state during usage.  This is so that inputs
        can be found to be equal or not based only on object "genetics".

        The value produced will be consistent across multiple invocations of
        the python interpreter (non-salted).
        """
        m = hashlib.sha256()
        
        # Iterate in sorted order to make a functional rather than literal hash.
        for k, v in sorted(self._all_metrics.items()):
            m.update(k.encode())
            m.update(repr(hash(v)).encode())

        h = m.digest()
        return int.from_bytes(h, byteorder='big', signed=False)

    def add_accumulator(self, name: str, accum: MetricTimeAccumulator):
        """ Adds a new time accumulator to this metric manager.

        If the supplied accumulator is None, this will actually remove an
        existing metric by name if one exists.
        
        Parameters
        ----------
        name : str
            The name to use as a key for the new accumulator.  This key can be
            used to get the accumulator back using get_accumulator.
        accum : MetricTimeAccumulator
            The new accumulator to map to the given name.  If this argument is
            None, then this actually may result in the removal of a metric.
        """
        if accum is not None:
            self._all_metrics[name] = accum
        else:
            self.remove_accumulator(name)

    def remove_accumulator(self, name: str) -> bool:
        """ Removes an existing time accumulator from this metric manager
        
        Parameters
        ----------
        name : str
            The key name that was used to add the accumulator that you now want
            to remove.

        Returns
        -------
        bool:
            True if an accumulator keyed on name is found and removed and false
            otherwise.
        """
        if name in self._all_metrics:
            del self._all_metrics[name]
            return True

        return False

    def get_accumulator(self, name: str) -> MetricTimeAccumulator:
        """Retrieves an existing time accumulator from this metric manager
           using the supplied name.
        
        Parameters
        ----------
        name : str
            The key name that was used to add the accumulator that you now want
            to access.
            
        Returns
        -------
        MetricTimeAccumulator:
            The metric accumulator associated with the supplied key or None.
        """
        return self._all_metrics.get(name)

    def to_dicts(self) -> list[dict]:
        """Return a list of dictionaries representing all of the metrics being
         managed by this manager.

        Returns
        -------
        dict
            A list of dictionaries representing all of the metrics managed by this manager.
        """
        return [
            accumulator.to_dict(name)
            for name, accumulator in self._all_metrics.items()
        ]

    def write_toml(self, category) -> str:
        """Writes the properties of this class instance to a string in TOML
           format.
        
        Parameters
        ----------
        category : str
            The category under which this metric manager is being stored if
            any. This would be passed in from a metric owner and is optional.
            If it is None, then the category tag will not be written.

        Returns
        -------
        str:
            A TOML formatted string with the properties of this instance.
        """
        ret = f"\n\n[metrics.\"{category}\"]\nvalues=["
        for accKey in self._all_metrics:
            accumulator = self._all_metrics[accKey]
            ret += accumulator.write_toml(category, accKey) + ",\n"

        ret += "]"
        return ret

    def read_toml(self, tomlData):
        """Reads the properties of this class instance from a TOML formated dictionary.

        Parameters
        -------
        tomlData
            A TOML formatted dictionary from which to read the properties of this class
            instance.
        """
        values = tomlData.get("values", [])
        for mDict in values:
            mta = MetricTimeAccumulator.read_toml(mDict)
            name = mDict.get("name", "unnamed")
            self.add_accumulator(name, mta)

    @property
    def all_metrics(self) -> dict:
        """Allows access to the mapping of all metrics in this manager.
        
        Returns
        -------
        dict:
            The map of all metrics with keys (names) mapped to MetricTimeAccumulator
            instances.
        """
        return self._all_metrics

    @property
    def get_total_accumulation(self) -> float:
        """Computes and returns the total accumulated metric value over all
           accumulators stored in this manager.
        
        Returns
        -------
        float:
            The sum of all accumulated values of all accumulators in this
            manager.
        """
        ret = 0.0
        for accumulator in self._all_metrics.values():
            ret += accumulator.accumulated_value
        return ret

# if __name__ == "__main__":
#    m_ = Metric(None, 1.05, 1.0, ImprovementType.Minimize)
#    m_.normalize(1.0)
