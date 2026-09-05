# Deal24H production build pipeline

The production Deal Bot is the only workflow allowed to publish canonical generated data to `main`.
Analytics must remain read-only with respect to the `main` branch so it cannot race the canonical publisher.
