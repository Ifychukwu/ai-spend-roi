# Methods

## Cost
- **Token cost** is priced per call from input, cached input and output tokens (`tokenroi.data.price`). Retries are billed like any other attempt, which is how providers bill.
- **Platform cost** (£6,000 a month: the share of the platform team, gateway and monitoring) is allocated to teams by share of requests. Allocation by tokens would push almost all of it onto Engineering; requests are a fairer proxy for the operational load each team creates. The choice is a parameter.
- **Total cost of ownership** = token cost + allocated platform cost.

## Time saved
- **Randomised pilot** (Customer Support, Claims): difference in mean handle time between the control and AI-assisted arms, with a 95% bootstrap interval (4,000 resamples). Randomisation is what makes this causal: without it, the staff who choose to use AI may simply be the faster ones.
- **Survey correction** for teams without a pilot: the self-reported figure is multiplied by the mean pilot-to-survey ratio of the pilot teams (0.51). The interval is widened by half the range of that ratio plus 0.10, because the correction assumes every team over-reports by about the same amount.

## Value and ROI
- Value = AI-assisted outcomes × minutes saved / 60 × loaded hourly cost. This values *capacity freed*, not cash saved: the saving only becomes cash if the freed time is redeployed or hiring is avoided. The README says so.
- ROI = (value − total cost) / total cost, with low and high values from the time-saved interval.

## Savings
- **Caching:** cache the fixed system prompt for every feature not already caching it, at the 93% hit rate observed in Customer Support.
- **Routing:** for each feature, the cheapest model whose offline acceptance rate is within 2 points of the model in use. Never route to a more expensive model.
- **Retry storm:** cost of attempts above the normal 1.5% failure rate during 11–24 May.

## Limitations
- Synthetic data; the method, SQL and dashboard are the deliverable.
- Offline acceptance rate is a proxy for production quality; route gradually with an A/B test.
- Weekly outcomes are assigned to the month their week starts in.
