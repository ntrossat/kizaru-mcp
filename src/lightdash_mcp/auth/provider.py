"""LightdashOAuthProvider: implements OAuthAuthorizationServerProvider (Phase 1).

Proxies sign-in to Lightdash OAuth, issues the server's own tokens, and maps them
to each user's Lightdash tokens stored encrypted in Redis.
"""
