"""
Environment Detection and URL Management Utility
Automatically detects environment and generates appropriate URLs
"""
import os
from typing import List, Optional
from enum import Enum


class Environment(str, Enum):
    """Environment types"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    DOCKER = "docker"


class EnvironmentConfig:
    """
    Smart environment detection and URL management.
    Automatically handles localhost, Docker, and production URLs.
    """
    
    @staticmethod
    def detect_environment() -> Environment:
        """Detect current environment"""
        # Check explicit environment variable
        env = os.getenv("ENVIRONMENT", "").lower()
        if env in ["production", "prod"]:
            return Environment.PRODUCTION
        if env in ["staging", "stage"]:
            return Environment.STAGING
        if env in ["docker"]:
            return Environment.DOCKER
        
        # Check if running in Docker
        if os.path.exists("/.dockerenv") or os.getenv("DOCKER_CONTAINER"):
            return Environment.DOCKER
        
        # Check if DEBUG is False (production indicator)
        if os.getenv("DEBUG", "True").lower() in ["false", "0", "no"]:
            return Environment.PRODUCTION
        
        # Default to development
        return Environment.DEVELOPMENT
    
    @staticmethod
    def get_domain() -> str:
        """Get domain name or IP address for the server"""
        # Check for explicit domain setting
        domain = os.getenv("DOMAIN_NAME")
        if domain:
            return domain
        
        # Check for PUBLIC_URL
        public_url = os.getenv("PUBLIC_URL")
        if public_url:
            # Extract domain from URL
            return public_url.replace("https://", "").replace("http://", "").split("/")[0]
        
        # Default based on environment
        env = EnvironmentConfig.detect_environment()
        if env == Environment.DOCKER:
            return "localhost"
        elif env == Environment.PRODUCTION:
            # In production, we should have a domain set
            return os.getenv("HOST", "0.0.0.0")
        else:
            return "localhost"
    
    @staticmethod
    def get_protocol() -> str:
        """Get protocol (http/https) based on environment"""
        # Check explicit setting
        use_https = os.getenv("USE_HTTPS", "").lower() in ["true", "1", "yes"]
        if use_https:
            return "https"
        
        # Check domain for SSL indicators
        domain = EnvironmentConfig.get_domain()
        if domain and not domain.startswith("localhost") and not domain.startswith("127.0.0.1"):
            # Production domain should use HTTPS
            env = EnvironmentConfig.detect_environment()
            if env == Environment.PRODUCTION:
                return "https"
        
        return "http"
    
    @staticmethod
    def get_backend_url(include_port: bool = True) -> str:
        """Get full backend URL"""
        protocol = EnvironmentConfig.get_protocol()
        domain = EnvironmentConfig.get_domain()
        port = os.getenv("PORT", "8000")
        
        # Don't include port for standard ports or production with reverse proxy
        env = EnvironmentConfig.detect_environment()
        if not include_port or (env == Environment.PRODUCTION and protocol == "https"):
            return f"{protocol}://{domain}"
        
        return f"{protocol}://{domain}:{port}"
    
    @staticmethod
    def get_frontend_url() -> str:
        """Get frontend URL"""
        # Check explicit setting
        frontend_url = os.getenv("FRONTEND_URL")
        if frontend_url:
            return frontend_url
        
        protocol = EnvironmentConfig.get_protocol()
        domain = EnvironmentConfig.get_domain()
        
        # Frontend typically runs on same domain in production
        env = EnvironmentConfig.detect_environment()
        if env == Environment.PRODUCTION:
            return f"{protocol}://{domain}"
        
        # Development - different port
        frontend_port = os.getenv("FRONTEND_PORT", "5173")
        return f"{protocol}://{domain}:{frontend_port}"
    
    @staticmethod
    def get_websocket_url() -> str:
        """Get WebSocket URL"""
        protocol = "wss" if EnvironmentConfig.get_protocol() == "https" else "ws"
        domain = EnvironmentConfig.get_domain()
        
        env = EnvironmentConfig.detect_environment()
        if env == Environment.PRODUCTION:
            return f"{protocol}://{domain}"
        
        port = os.getenv("PORT", "8000")
        return f"{protocol}://{domain}:{port}"
    
    @staticmethod
    def get_cors_origins() -> List[str]:
        """Get CORS origins based on environment"""
        # Check explicit setting
        cors_env = os.getenv("BACKEND_CORS_ORIGINS")
        if cors_env:
            return [origin.strip() for origin in cors_env.split(",") if origin.strip()]
        
        # Build CORS list based on environment
        env = EnvironmentConfig.detect_environment()
        domain = EnvironmentConfig.get_domain()
        protocol = EnvironmentConfig.get_protocol()
        
        origins = []
        
        if env == Environment.PRODUCTION:
            # Production origins
            origins.extend([
                f"https://{domain}",
                f"https://www.{domain}",
                f"http://{domain}",  # Redirect to HTTPS
                f"http://www.{domain}",  # Redirect to HTTPS
            ])
        else:
            # Development origins
            port = os.getenv("PORT", "8000")
            origins.extend([
                f"http://localhost:{port}",
                "http://localhost:3000",
                "http://localhost:5173",  # Vite default
                "http://127.0.0.1:3000",
                "http://127.0.0.1:5173",
                f"http://127.0.0.1:{port}",
            ])
        
        return list(set(origins))  # Remove duplicates
    
    @staticmethod
    def get_api_docs_url() -> str:
        """Get API documentation URL"""
        base_url = EnvironmentConfig.get_backend_url(include_port=True)
        return f"{base_url}/docs"
    
    @staticmethod
    def print_environment_info():
        """Print current environment configuration (for debugging)"""
        env = EnvironmentConfig.detect_environment()
        print("=" * 60)
        print("🌍 ENVIRONMENT CONFIGURATION")
        print("=" * 60)
        print(f"Environment:     {env.value}")
        print(f"Domain:          {EnvironmentConfig.get_domain()}")
        print(f"Protocol:        {EnvironmentConfig.get_protocol()}")
        print(f"Backend URL:     {EnvironmentConfig.get_backend_url()}")
        print(f"Frontend URL:    {EnvironmentConfig.get_frontend_url()}")
        print(f"WebSocket URL:   {EnvironmentConfig.get_websocket_url()}")
        print(f"API Docs:        {EnvironmentConfig.get_api_docs_url()}")
        print(f"CORS Origins:    {len(EnvironmentConfig.get_cors_origins())} origins")
        for origin in EnvironmentConfig.get_cors_origins():
            print(f"  - {origin}")
        print("=" * 60)


# Convenience functions
def get_backend_url() -> str:
    """Get backend URL"""
    return EnvironmentConfig.get_backend_url()


def get_frontend_url() -> str:
    """Get frontend URL"""
    return EnvironmentConfig.get_frontend_url()


def get_websocket_url() -> str:
    """Get WebSocket URL"""
    return EnvironmentConfig.get_websocket_url()


def get_cors_origins() -> List[str]:
    """Get CORS origins"""
    return EnvironmentConfig.get_cors_origins()


def is_production() -> bool:
    """Check if running in production"""
    return EnvironmentConfig.detect_environment() == Environment.PRODUCTION


def is_development() -> bool:
    """Check if running in development"""
    return EnvironmentConfig.detect_environment() == Environment.DEVELOPMENT
