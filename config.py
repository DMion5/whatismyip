# Basic configuration file
import os

class Config(object):
    DEBUG = False
    TESTING = False

    SECRET_KEY = os.getenv(
        'FLASK_SECRET_KEY',
        # safe value used for development when FLASK_SECRET_KEY might not be set
        '9e4@&tw46$l31)zrqe3wi+-slqm(ruvz&se0^%9#6(_w3ui!c0'
    )

class ProductionConfig(Config):
    pass

class DevelopmentConfig(Config):
    DEBUG = True

class TestingConfig(Config):
    TESTING = True