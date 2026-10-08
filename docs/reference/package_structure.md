---
hide:
#  - navigation
#  - toc
---

# Package Structure

## Main Namespaces

Namespaces needed for building and operating the trading infrastructure.

<div class="grid cards" markdown>

-   __.brokers__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `brokers` package API](brokers/base.md)

-   __.datafeeds__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `datafeeds` package API](datafeeds/base.md)

-   __.domain__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `domain` package API](domain/constants.md)

-   __.indicators__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `indicators` package API](indicators/bar_fields.md)

-   __.messaging__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `messaging` package API](messaging/backtest_eventbus.md)

-   __.recorders__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `recorders` package API](recorders/base.md)

-   __.strategies__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `strategies` package API](strategies/base.md)

</div>

## Special-Purpose Namespaces 

Namespaces containing internal plumbing that usually does not need to be touched during 
regular operation as well as some useful tools that might come in handy during the
strategy development lifecycle. 

<div class="grid cards" markdown>

-   __.data__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `data` package API](data/databento.md)

-   __.utils__&nbsp;&nbsp;

    ---

    [:material-link-variant: View `utils` package API](utils/post_init_hook.md)

</div>
