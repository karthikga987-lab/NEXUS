from app.db.session import Base, engine
from app.models import Company, SourceDocument, ProductEvent, EventRelationship, Proposal, Feedback

def init_db():
    Base.metadata.create_all(bind=engine)
