from __future__ import annotations
import enum
import math

@enum.unique
class ImprovementType(int, enum.Enum):
    """An enumeration that is used to indicate the "sense" for a metric.

    This indicates whether a metric is better when minimized, maximized, etc.
    """
    Minimize = 0
    Maximize = 1
    SeekValue = 2
    
    @staticmethod
    def parse(str: str):
        """A utility method to parse a string into a member of the
           ImprovementType enumeration.

        This will match the words minimize, min, maximize, max, seek value,
        seekvalue, seek, and the digits 0, 1, and 2.  The matching is case
        insensitive.

        Parameters
        ----------
        str :
            The string to try and parse into a member of the ImprovementType
            enumeration.

        Returns
        -------
        Improvement Type
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

def get_default_improvement_type(limit: float, objective: float):
    """A utility method to choose an appropriate improvement type based on the
       supplied limit and objective.

    Parameters
    ----------
    limit :
        The worst acceptable value for the metric.
    objective :
        The target value which if obtained, provides full satisfaction.

    Returns
    -------
    ImprovementType
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
    """A class used to normalize metric values for subsequence combination and
       comparison.

    Parameters
    ----------
    limit : float
        The worst acceptable value for the metric.
    objective : float
        The target value which if obtained, provides full satisfaction.
    imp_type : ImprovementType
        The desired sense of the metric such as Minimize or Maximize.

        This input must be compatible with the limit and objective.  For
        example, if the imp_type is Minimize, then the limit must be greater
        than the objective. These relationships are asserted.

        If this input is not provided, then a default is determined based on
        the limit and objective.
    a : float
        The parameter that controls the curvature of the normalization function
        below the limit (on the bad side of the limit).  It is recommended that
        you use the default value.
    b : float
        The parameter that controls the slope of the normalization curve at the
        limit.  It is recommended that you use the default value.
    c : float
        Sets the normalized value (y value) at the limit.  It is recommended
        that you use the default value.
    g : float
        The parameter that controls the curvature of the normalization function
        above the objective (on the good side of the objective).  It is
        recommended that you use the default value.
    """
    def __init__(
        self,
        limit: float,
        objective: float,
        imp_type: ImprovementType = None,
        a: float=5.0,
        b: float=5.0,
        c: float=0.0,
        g: float=0.2
    ):
        self._limit = limit
        self._objective = objective
        self._imp_type = imp_type

        if imp_type is None:
            self._imp_type = get_default_improvement_type(
                self._limit, self._objective
                )

        self._a = a
        self._b = b
        self._c = c
        self._g = g
        self._validate_inputs()
                
    @property
    def limit(self) -> float:
        """Allows access to the supplied limit value for this metric.

        Returns
        -------
        Limit
            The worst acceptable value for this metric.
        """
        return self._limit
    
    @property
    def objective(self) -> float:
        """Allows access to the supplied objective value for this metric.

        Returns
        -------
        Objective
            The value that provides full satisfaction for this metric.
        """
        return self._objective
    
    @property
    def improvement_type(self) -> ImprovementType:
        """Allows access to the supplied improvement type or "sense" for this
           metric.

        Returns
        -------
        Improvement Type
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
        tomlData
            The dictionary that contains the metric properties from which to
            create a new metric instance.  The minimum set of keys that must
            be present are "limit", "objective", and "sense".  "sense" must
            point to something that can be parsed to an ImprovementType
            enumeration value.

        Returns
        -------
        Metric
            A newly created metric made using the properties in the supplied
            TOML dictionary.
        """
        limit = tomlData["limit"]
        objective = tomlData["objective"]
        impType = ImprovementType.parse(tomlData["sense"])
        return Metric(limit, objective, impType)
    
    def write_toml(self, category, key) -> str:
        """Writes the properties of this class instance to a string in TOML
           format.
        
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
        Limit
            A TOML formatted string with the properties of this instance.
        """
        ret = f"\n\n[metrics.{category}.{key}]\n"
        ret += f"limit = {str(self._limit)}\n"
        ret += f"objective = {str(self._objective)}\n"
        ret += f"sense = \"{str(self._imp_type.name)}\"\n"
        return ret

    def normalize(self, value: float) -> float:
        """Convert a raw metric value into a normalized fitness value.

        Parameters
        ----------
        value : float
            The raw metric value in natural units.

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied raw value, this metrics
            limit and objective, and the other curve parameters of this metric.
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
        NormalizedValue
            A normalized value based on the supplied raw value, this metrics
            limit and objective, and the other curve parameters of this metric.
            this does calculations for a metric meant for minimization.
        """
        return self.__do_max_norm__(-value, -self._limit, -self._objective)

    def _normalize_for_maximization(self, value: float) -> float:
        """Convert a raw metric value into a normalized fitness value for a
           maximization metric.

        Parameters
        ----------
        value : float
            The raw metric value in natural units.

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied raw value, this metrics
            limit and objective, and the other curve parameters of this metric.
            this does calculations for a metric meant for maximization.
        """
        return self.__do_max_norm__(value, self._limit, self._objective)

    def _normalize_for_seek_value(self, value: float) -> float:
        """Convert a raw metric value into a normalized fitness value for a
           seek value metric.

        Parameters
        ----------
        value : float
            The raw metric value in natural units.

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied raw value, this metrics
            limit and objective, and the other curve parameters of this metric.
            this does calculations for a metric meant for seek value.
        """
        biz_lim = self._objective - (self._limit - self._objective)

        use_lim = min(self._limit, biz_lim) if value <= self._objective else \
            max(self._limit, biz_lim)

        if value <= self._objective:
            return self.__do_max_norm__(value, use_lim, self._objective)

        return self.__do_max_norm__(-value, -use_lim, -self._objective)

    def _violated(self, norm_val: float):
        """Calculates the normalized value of a pre-normalized metric value
           that falls in the region of the space below (or worse than) the
           limit.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that
            is to be normalized.  It must have been a metric value in the
            violated region (worse than the limit).

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied pre-normalized value, this
            metrics limit and objective, and the other curve parameters of this
            metric.
        """
        return -(self._a * norm_val * norm_val) / 2.0 + \
            self._b * norm_val + self._c

    def _feasible(self, norm_val: float) -> float:
        """Calculates the normalized value of a pre-normalized metric value
           that falls in the region between the limit and the objective.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that
            is to be normalized.  It must have been a metric value in the
            region between the limit and the objective.

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied pre-normalized value, this
            metrics limit and objective, and the other curve parameters of this
            metric.
        """
        d = self._d()
        return d * math.sqrt(norm_val + self._f(d)) + self._c - self._psi(d)

    def _super_optimal(self, norm_val: float) -> float:
        """Calculates the normalized value of a pre-normalized metric value
           that falls in the region above the objective.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that
            is to be normalized.  It must have been a metric value in the
            region above the objective.

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied pre-normalized value, this
            metrics limit and objective, and the other curve parameters of this
            metric.
        """
        h = self._h(self._d())
        return self._g * math.sqrt(norm_val + h - 1.0) - self._phi(h) + 1.0

    def _d(self) -> float:
        '''An intermediate value used in several places during normalization.'''
        x = 1.0 - 2.0 * self._c + self._c * self._c
        y = self._c + self._b - 1.0
        return math.sqrt(self._b * x / y)

    def _f(self, d: float) -> float:
        '''An intermediate value used in several places during normalization.'''
        val = d / (2.0 * self._b)
        return val * val

    def _psi(self, d: float) -> float:
        '''An intermediate value used in several places during normalization.'''
        return (d * d) / (2.0 * self._b)

    def _h(self, d: float) -> float:
        '''An intermediate value used in several places during normalization.'''
        return (self._g * self._g * (self._f(d) + 1.0)) / (d * d)

    def _phi(self, h: float) -> float:
        '''An intermediate value used in several places during normalization.'''
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
            The raw value of a metric that is in the process of being
            normalized.
        limit : float
            The worst acceptable value for the metric.
        objective : float
            The target value which if obtained, provides full satisfaction.

        Returns
        -------
        Pre-Normalized Value
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
        Normalized Value
            The result of normalizing the value for maximization.
        """
        resp_norm = Metric._do_pre_normalization(value, limit, objective)

        if value < limit:
            return self._violated(resp_norm)
        if value < self._objective:
            return self._feasible(resp_norm)
        return self._super_optimal(resp_norm)

    def _validate_inputs(self, do_assert: bool = True):
        """Tests the validity/usability of the values stored in this metric.

        This uses the static validate_metric_values method.  See it for
        details.
        
        Parameters
        ----------
        do_assert : bool
            A flag that indicates whether this method should throw an exception
            (true) or return an error message as a string (false).

        Returns
        -------
        Error String or None
            This method either throws an exception or returns a string
            depending on the value of do_assert.  Either way, the message is
            determined using the conditions laid out in the description.
            
        Raises
        ------
        AssertionError
            If any of the conditions listed in the description are present and
            the do_assert parameter is set to true.
        """
        Metric.validate_metric_values(
            self._limit, self._objective, self._imp_type, do_assert
            )
            
    @staticmethod
    def validate_metric_values(
        limit: float, objective: float, imp_type: ImprovementType,
        do_assert: bool = False
        ):
        """Tests the validity/usability of the metric values provided.

        This will either return an error string or throw an exception with an
        error message.  Which it does will be determined by the do_assert
        parameter.  The requirements are that first: none of the parameters can
        be none.  Second, if the imp_type is minimize, the limit must be
        greater than the objectve. if the imp_type is maximize, the limit must
        be less than the objective and no matter the imp_type, the limit cannot
        equal the objective.
        
        Parameters
        ----------
        limit : float
            The worst acceptable value for a metric.
        objective : float
            The target value which if obtained, provides full satisfaction.
        imp_type : ImprovementType
            The desired sense of a metric such as Minimize or Maximize.
        do_assert : bool
            A flag that indicates whether this method should throw an exception
            (true) or return an error message as a string (false).

        Returns
        -------
        Error String or None
            This method either throws an exception or returns a string
            depending on the value of do_assert.  Either way, the message is
            determined using the conditions laid out in the description.
            
        Raises
        ------
        AssertionError
            If any of the conditions listed in the description are present and
            the do_assert parameter is set to true.
        """
        try:
            assert limit != None, \
                "A value must be provided for the limit."
            
            assert objective != None, \
                "A value must be provided for the objective."
            
            assert imp_type != None, \
                "A value must be provided for the sense."

            if imp_type == ImprovementType.Minimize:
                assert limit > objective, \
                    "Limit must be greater than objective for minimization"

            elif imp_type == ImprovementType.Maximize:
                assert limit < objective, \
                    "Limit must be less than objective for maximization"

            else:
                assert limit != objective, \
                    "Limit cannot be equal to objective."

            return None
        except AssertionError as err:
            if do_assert:
                raise

            return str(err)


class MetricAccumulator:
    """A class used to accumulate a normalize metric value over time.

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
        Normalized Value
            The result of normalizing the supplied value parameter.
        """
        if d_time == 0.0: return 0.0
        met_val = self._metric.normalize(value)
        self._total_time += d_time
        self._accumulated += d_time * met_val
        return met_val
    
    def write_toml(self, category, key) -> str:
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
        Limit
            A TOML formatted string with the properties of this instance.
        """
        return self._metric.write_toml(category, key)
    
    @staticmethod
    def read_toml(tomlData) -> MetricAccumulator:
        """Reads the properties of a metric accumulator class instance from a
           TOML formatted dictionary and creates and returns a new
           MetricAccumulator instance.
        
        Parameters
        ----------
        tomlData
            The dictionary that contains the metric accumulator properties from
            which to create a new instance.  The minimum set of keys that must
            be present are only those associated with a Metric.

        Returns
        -------
        Metric Accumulator
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
        Accumulated Value
            The current time weighted sum of normalized values.
        """
        return self._accumulated

    @property
    def total_time(self) -> float:
        """Allows access to the current sum of all accumulated time.

        Returns
        -------
        Total Time
            The current sum of all accumulated time.
        """
        return self._total_time

    @property
    def denormalized_value(self) -> float:
        """Allows access to the current total accumulation divided by the total
           time.

        Returns
        -------
        TotalTime
            The current total accumulation over the total time accumulated so
            far.
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
    init_time :
        The time to be the initial "current time" for this accumulator.
        The default is 0.
    """
    def __init__(self, m: Metric, init_time=0.0):
        MetricAccumulator.__init__(self, m)
        self._curr_time = init_time
            
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
        Metric Time Accumulator
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
        Normalized Value
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
        Accumulator
            The metric accumulator associated with the supplied key or None.
        """
        return self._all_metrics.get(name)

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
        Limit
            A TOML formatted string with the properties of this instance.
        """
        ret = ""
        for accKey in self._all_metrics:
            accumulator = self._all_metrics[accKey]
            ret += accumulator.write_toml(category, accKey)

        return ret
         
    @property
    def all_metrics(self) -> dict:
        """Allows access to the mapping of all metrics in this manager.
        
        Returns
        -------
        Metric Map
            The map has string keys (names) mapped to MetricTimeAccumulator
            instances.
        """
        return self._all_metrics
    
    @property
    def get_total_accumulation(self) -> float:
        """Computes and returns the total accumulated metric value over all
           accumulators stored in this manager.
        
        Returns
        -------
        Total Accumulation
            The sum of all accumulated values of all accumulators in this
            manager.
        """
        ret = 0.0
        for accumulator in self._all_metrics.values():
            ret += accumulator.accumulated_value
        return ret


# if __name__ == "__main__":
#    m_ = Metric(1.05, 1.0, ImprovementType.Minimize)
#    m_.normalize(1.0)
