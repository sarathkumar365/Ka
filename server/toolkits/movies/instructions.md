Movies toolkit.

- Taste: when the owner states a like or dislike, save it with remember(toolkit="movies"), with
  the film, liked or disliked, and why. When you only infer it, use propose_memory(toolkit="movies").
- New releases: movies_discover (use genre ids; default is the last year). Search by title with
  movies_search. Recommend from the owner's taste in the movies memory, and say why each fits.
- Availability: movies_where_to_watch for Canada (streaming, rental, purchase). If a service is
  missing or the data looks old, check with web_search.
- Always end with: "Data from TMDB; where-to-watch from JustWatch."
