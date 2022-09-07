import enum
import math

@enum.unique
class ImprovementType(int, enum.Enum):
    Minimize = 0
    Maximize = 1
    SeekValue = 2
    
    @staticmethod
    def parse(str):
        toParse = str.casefold()
        if toParse == "Minimize".casefold():
            return ImprovementType.Minimize
        
        if toParse == "Min".casefold():
            return ImprovementType.Minimize

        if toParse == "Maximize".casefold():
            return ImprovementType.Maximize
        
        if toParse == "Max".casefold():
            return ImprovementType.Maximize

        if toParse == "Seek Value".casefold():
            return ImprovementType.SeekValue
        
        if toParse == "Seek".casefold():
            return ImprovementType.SeekValue

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
        objective, ImprovementType.Maximize if the limit is greater than the objective,
        and None if the limit is equal to the objective.
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
    limit :
        The worst acceptable value for the metric.
    objective :
        The target value which if obtained, provides full satisfaction.
    imp_type :
        The desired sense of the metric such as Minimize or Maximize.

        This input must be compatible with the limit and objective.  For example,
        if the imp_type is Minimize, then the limit must be greater than the
        objective. These relationships are asserted.

        If this input is not provided, then a default is determined based on
        the limit and objective.
    a :
        The parameter that controls the curvature of the normalization function
        below the limit (on the bad side of the limit).  It is recommended that
        you use the default value.
    b :
        The parameter that controls the slope of the normalization curve at the
        limit.  It is recommended that you use the default value.
    c :
        Sets the normalized value (y value) at the limit.  It is recommended that
        you use the default value.
    g :
        The parameter that controls the curvature of the normalization function
        above the objective (on the good side of the objective).  It is recommended
        that you use the default value.
    """
    def __init__(
            self,
            limit: float,
            objective: float,
            imp_type: ImprovementType = None,
            a=5.0,
            b=5.0,
            c=0.0,
            g=0.2
    ):
        self._limit = limit
        self._objective = objective
        self._imp_type = imp_type

        if imp_type is None:
            self._imp_type = get_default_improvement_type(self._limit, self._objective)

        self._a = a
        self._b = b
        self._c = c
        self._g = g
        self._validate_inputs()

        
    @property
    def limit(self) -> float:
        return self._limit
    
    @property
    def objective(self) -> float:
        return self._objective
    
    @property
    def improvement_type(self) -> ImprovementType:
        return self._imp_type

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
        """Calculates the normalized value of a pre-normalized metric value that
           falls in the region of the space below (or worse than) the limit.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that is to
            be normalized.  It must have been a metric value in the violated region
            (worse than the limit).

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied pre-normalized value, this metrics
            limit and objective, and the other curve parameters of this metric.
        """
        return -(self._a * norm_val * norm_val) / 2.0 + self._b * norm_val + self._c

    def _feasible(self, norm_val: float) -> float:
        """Calculates the normalized value of a pre-normalized metric value that
           falls in the region between the limit and the objective.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that is to
            be normalized.  It must have been a metric value in the region between the
            limit and the objective.

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied pre-normalized value, this metrics
            limit and objective, and the other curve parameters of this metric.
        """
        d = self._d()
        return d * math.sqrt(norm_val + self._f(d)) + self._c - self._psi(d)

    def _super_optimal(self, norm_val: float) -> float:
        """Calculates the normalized value of a pre-normalized metric value that
           falls in the region above the objective.

        Parameters
        ----------
        norm_val : float
            The metric value that has already undergone pre-normalization that is to
            be normalized.  It must have been a metric value in the region above the
            objective.

        Returns
        -------
        NormalizedValue
            A normalized value based on the supplied pre-normalized value, this metrics
            limit and objective, and the other curve parameters of this metric.
        """
        h = self._h(self._d())
        return self._g * math.sqrt(norm_val + h - 1.0) - self._phi(h) + 1.0

    def _d(self) -> float:
        x = 1.0 - 2.0 * self._c + self._c * self._c
        y = self._c + self._b - 1.0
        return math.sqrt(self._b * x / y)

    def _f(self, d: float) -> float:
        val = d / (2.0 * self._b)
        return val * val

    def _psi(self, d: float) -> float:
        return (d * d) / (2.0 * self._b)

    def _h(self, d: float) -> float:
        return (self._g * self._g * (self._f(d) + 1.0)) / (d * d)

    def _phi(self, h: float) -> float:
        return self._g * math.sqrt(h)

    @staticmethod
    def _do_pre_normalization(raw_value: float, limit: float, objective: float) -> float:
        return (raw_value - limit) / (objective - limit)

    def __do_max_norm__(self, value: float, limit: float, objective: float) -> float:
        resp_norm = Metric._do_pre_normalization(value, limit, objective)

        if value < limit:
            return self._violated(resp_norm)
        if value < self._objective:
            return self._feasible(resp_norm)
        return self._super_optimal(resp_norm)

    def _validate_inputs(self):
        if self._imp_type == ImprovementType.Minimize:
            assert self._limit > self._objective, \
                "Limit must be greater than objective for minimization"

        elif self._imp_type == ImprovementType.Maximize:
            assert self._limit < self._objective, \
                "Limit must be less than objective for maximization"

        else:
            assert self._limit != self._objective, \
                "Limit cannot be equal to objective."


class MetricAccumulator:

    def __init__(self, m: Metric):
        self._metric = m
        self._accumulated = 0.0
        self._total_time = 0.0

    def accumulate(self, value: float, d_time: float) -> float:
        """Adds in normalized value weighted by the amount of time provided.

        Parameters
        ----------
        value : float
            The raw metric value to be normalized and accumulated into this accumulator.
            This value will be normalized by the contained Metric.
        d_time: float
            The amount of time over which the provided value applies.  This is used as
            a weighting factor in the accumulation.
        """
        if d_time == 0.0:
            return 0.0
        met_val = self._metric.normalize(value)
        self._total_time += d_time
        self._accumulated += d_time * met_val
        return met_val

    @property
    def accumulated_value(self) -> float:
        """Allows access to the current accumulation value.  This is the time weighted sum
        of normalized values.

        Returns
        -------
        AccumulatedValue
            The current time weighted sum of normalized values.
        """
        return self._accumulated

    @property
    def total_time(self) -> float:
        """Allows access to the current sum of all accumulated time.

        Returns
        -------
        TotalTime
            The current sum of all accumulated time.
        """
        return self._total_time

    @property
    def denormalized_value(self) -> float:
        """Allows access to the current total accumulation divided by the total time.

        Returns
        -------
        TotalTime
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

    def __init__(self, m: Metric, init_time=0.0):
        MetricAccumulator.__init__(self, m)
        self._curr_time = init_time

    def accumulate(self, value: float, curr_time: float) -> float:
        """Adds in normalized value weighted by the difference between the last
        time this method was called and the time provided.

        Parameters
        ----------
        value : float
            The raw metric value to be normalized and accumulated into this accumulator.
            This value will be normalized by the contained Metric.
        curr_time: float
            The simulation time of this call to be used along with the last time this
            method was called for accumulation purposes.
        """
        assert curr_time >= self._curr_time, \
            "current time provided to accumulate function must be greater than " + \
            "or equal to any prior time provided."
        if curr_time == self._curr_time:
            return 0.0
        val = MetricAccumulator.accumulate(self, value, curr_time - self._curr_time)
        self._curr_time = curr_time
        return val


class MetricManager:

    def __init__(self):
        self._all_metrics = {}

    def add_accumulator(self, name: str, accum: MetricTimeAccumulator):
        """
        :param name: The name to which the accumulator is keyed.
        :param accum: MetricTimeAccumulator
        :return: None
        """
        self._all_metrics[name] = accum

    def get_accumulator(self, name: str):
        """
        :param name: The name to which the accumulator is keyed.
        :return: The metric accumulator associated with the supplied key or None.
        """
        return self._all_metrics.get(name)
        

    @property
    def all_metrics(self) -> dict:
        return self._all_metrics

    def __getitem__(self, name: str):
        return self._all_metrics.get(name)

    @property
    def get_total_accumulation(self) -> float:
        ret = 0.0
        for accumulator in self._all_metrics.values():
            ret += accumulator.accumulated_value
        return ret


# if __name__ == "__main__":
#    m_ = Metric(1.05, 1.0, ImprovementType.Minimize)
#    m_.normalize(1.0)
