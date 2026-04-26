from .base import Base, Column, String, Integer, Text


class NonActivityRecord(Base):
    __tablename__ = "non_activity_records"

    activity_id = Column(String(255), primary_key=True)
    title = Column(String(1000), nullable=False)
    college_id = Column(String(255), index=True)
    college_name = Column(String(255))
    source_url = Column(String(500))
    source_type = Column(String(50))
    source_channel = Column(String(50), default="wechat")
    mp_name = Column(String(255))
    publish_time = Column(Integer)
    activity_date = Column(String(20), index=True)
    activity_time = Column(String(100))
    location = Column(String(500))
    description = Column(Text)
    cover_image = Column(String(500))
    classification_reason = Column(String(255))
    body_preview = Column(Text)
    archived_at = Column(Integer, index=True)

    def to_dict(self) -> dict:
        return {
            "activity_id": self.activity_id,
            "title": self.title,
            "college_id": self.college_id,
            "college_name": self.college_name,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "source_channel": self.source_channel,
            "mp_name": self.mp_name,
            "publish_time": self.publish_time,
            "activity_date": self.activity_date,
            "activity_time": self.activity_time,
            "location": self.location,
            "description": self.description,
            "cover_image": self.cover_image,
            "classification_reason": self.classification_reason,
            "body_preview": self.body_preview,
            "archived_at": self.archived_at,
        }
