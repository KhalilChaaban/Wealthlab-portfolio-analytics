# Project reflection

## Why I started

I started WealthLab to build my understanding of portfolio analysis, private
banking, and financial risk. I want to understand how portfolios respond to
changing market conditions and use that knowledge to make more informed
financial decisions.

I'm also interested in what sits behind the numbers: the assumptions we make,
the details we overlook, and the biases that influence how we interpret results.
This project gives me a way to question those assumptions and practice
presenting findings honestly, including their limitations.

## How I approached it

I chose to use AI to support the coding and documentation because I wanted early
experience of combining financial analysis with technology as a student.

My goal was to develop practical skills I could carry into my career. Working
through the notebook, switching to Yahoo Finance data, and reviewing the results
gave me a starting point. I want to build on that experience by becoming more
confident with Python, checking calculations, and explaining the financial
reasoning behind the outputs.

## Challenges I worked through with guidance

### Getting comfortable with Colab

Part of the learning was practical: finding the right cells, running the
notebook, reading the output, and saving the right files. When the tests printed
red text, I initially needed help interpreting it. Finding `OK` at the end
helped me understand that the final test status mattered more than the color
of the output.

### Moving from demonstration data to real market data

I wanted the final case to use Yahoo Finance prices. Making that change raised
questions about date coverage, missing observations, adjusted prices, and what
the downloaded data actually represented. The project includes checks for these
issues, and understanding the reasons behind those checks is part of my
ongoing learning.

### Interpreting the return and risk trade-off

One question to work through was why the broader portfolio earned less than the
60/40 benchmark even though it had lower volatility. In the saved case, the
annualized returns were 6.83% and 8.39%, while volatility was 9.38% and 10.93%.
This made it important to consider return and risk together when discussing
diversification.

### Following the financial calculations

Following how returns, trading costs, and advisory fees flow into ending
portfolio value took care. The project uses automated tests and a reconciliation
of investment P&L, costs, and ending wealth. Running those checks was useful,
but I still want more practice checking the calculations myself and explaining
the timing and units involved.

### Separating history from simulation

I had to keep two parts of the project separate: the historical portfolio
backtest and the fictional client's future spending scenarios. The Yahoo data
describes past prices. The planning model uses chosen return, volatility, and
inflation assumptions. Its success frequencies depend on those assumptions and
are not predictions of what a client will experience.

### Keeping the written report consistent

Changing the data source also meant updating the written findings. The early
discussion used demonstration numbers, so it needed to be replaced when the
Yahoo results became the final case. Getting the charts, tables, and discussion
to describe the same run was part of finishing the project.

## Contributions

AI supported the implementation, tests, documentation, and repository setup. My
involvement included running the project in Colab, choosing to use real Yahoo
data, and working through the outputs with guidance. This reflection uses my
stated motivation and selected challenges, with AI assistance in editing.

## What I want to investigate next

I want to make the data checks more specific by comparing the dates in the price
history with the expected exchange sessions. I'd also like a report showing
each check's result, threshold, status, and evidence. That would help me follow
why a check passed or failed and decide what needs attention.

I'm also curious about how much the rebalancing rule affects the results. I'd
like to compare monthly, quarterly, and buy-and-hold policies across different
historical periods, using the same starting allocation and cost assumptions.
It seems like a useful way to question whether a conclusion holds beyond one
rule or one period, and to give myself more practice explaining the results.

These are planned extensions. They have not been implemented or evaluated in
the current case.
