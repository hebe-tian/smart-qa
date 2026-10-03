"""QA blueprint: multi-round requirement clarification (Feature 1)."""
from flask import Blueprint, request, jsonify, g
from app.extensions import db
from app.models.requirement import Requirement
from app.models.qa_session import QAMessage
from app.services.case_service import case_service
from app.core.decorators import token_required
from app.core.ownership import check_requirement_owner
from app.services.logging_service import get_logger

qa_bp = Blueprint("qa", __name__)
logger = get_logger("api")


@qa_bp.route("/analyze/<int:req_id>", methods=["POST"])
@token_required
def analyze_requirement(req_id):
    """Step 1: AI analyzes requirement and returns clarification questions if needed."""
    req = check_requirement_owner(req_id)

    try:
        req.status = "analyzing"
        db.session.commit()

        result = case_service.analyze_requirement(req, g.current_user_id)

        need_clarification = result.get("need_clarification", False)
        questions = result.get("clarification_points", [])

        if need_clarification and questions:
            # Save AI questions as assistant messages
            round_num = _get_next_round(req_id)
            qa_msg = QAMessage(
                requirement_id=req_id,
                role="assistant",
                content="\n\n".join(questions),
                round=round_num,
            )
            db.session.add(qa_msg)
            req.status = "qa"
            db.session.commit()

            logger.info("Analysis done: req_id=%d, needs clarification", req_id)

            # Track event
            from app.services.analytics_service import AnalyticsService
            AnalyticsService().track_event(
                user_id=g.current_user_id,
                event_type="qa_round",
                event_data={"requirement_id": req_id, "round": round_num},
            )

            return jsonify({
                "need_clarification": True,
                "questions": questions,
                "analysis_summary": result.get("analysis_summary", ""),
                "qa_messages": [m.to_dict() for m in QAMessage.query.filter_by(requirement_id=req_id).order_by(QAMessage.round).all()],
            })
        else:
            req.status = "qa"  # Ready for generation
            db.session.commit()
            logger.info("Analysis done: req_id=%d, ready for generation", req_id)
            return jsonify({
                "need_clarification": False,
                "analysis_summary": result.get("analysis_summary", ""),
                "message": "Requirement is clear. Ready to generate modules and test cases.",
            })

    except ValueError as e:
        req.status = "draft"
        db.session.commit()
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("Analyze failed: req_id=%d error=%s", req_id, str(e))
        req.status = "draft"
        db.session.commit()
        return jsonify({"error": "Analysis failed. Please try again."}), 500


@qa_bp.route("/answer/<int:req_id>", methods=["POST"])
@token_required
def submit_answer(req_id):
    """Step 2: User submits answers, AI either asks more questions or confirms sufficient."""
    req = check_requirement_owner(req_id)
    data = request.get_json() or {}
    answer = data.get("answer", "").strip()

    if not answer:
        return jsonify({"error": "Answer is required"}), 400

    try:
        round_num = _get_next_round(req_id)

        # Save user's answer
        user_msg = QAMessage(
            requirement_id=req_id,
            role="user",
            content=answer,
            round=round_num,
        )
        db.session.add(user_msg)
        db.session.commit()

        # AI determines if context is sufficient or asks more
        result = case_service.qa_followup(req, g.current_user_id)

        context_sufficient = result.get("context_sufficient", False)
        next_questions = result.get("next_questions", [])

        if not context_sufficient and next_questions:
            # Save AI's follow-up questions
            ai_msg = QAMessage(
                requirement_id=req_id,
                role="assistant",
                content="\n\n".join(next_questions),
                round=round_num,
            )
            db.session.add(ai_msg)
            req.status = "qa"
            db.session.commit()

            logger.info("QA round %d: needs more clarification", round_num)
            return jsonify({
                "context_sufficient": False,
                "next_questions": next_questions,
                "reasoning": result.get("reasoning", ""),
                "qa_messages": [m.to_dict() for m in QAMessage.query.filter_by(requirement_id=req_id).order_by(QAMessage.round, QAMessage.id).all()],
            })
        else:
            req.status = "generating"
            db.session.commit()
            logger.info("QA completed: req_id=%d context sufficient", req_id)

            # Track event
            from app.services.analytics_service import AnalyticsService
            AnalyticsService().track_event(
                user_id=g.current_user_id,
                event_type="generate_start",
                event_data={"requirement_id": req_id},
            )

            return jsonify({
                "context_sufficient": True,
                "reasoning": result.get("reasoning", ""),
                "message": "Context is sufficient. You can now generate modules and test cases.",
                "qa_messages": [m.to_dict() for m in QAMessage.query.filter_by(requirement_id=req_id).order_by(QAMessage.round, QAMessage.id).all()],
            })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error("QA answer failed: req_id=%d error=%s", req_id, str(e))
        return jsonify({"error": "QA processing failed. Please try again."}), 500


@qa_bp.route("/<int:req_id>/history", methods=["GET"])
@token_required
def get_qa_history(req_id):
    """Get all QA messages for a requirement."""
    check_requirement_owner(req_id)
    messages = QAMessage.query.filter_by(requirement_id=req_id).order_by(
        QAMessage.round, QAMessage.id
    ).all()
    return jsonify({"messages": [m.to_dict() for m in messages]})


def _get_next_round(requirement_id):
    """Get the next round number."""
    last = QAMessage.query.filter_by(requirement_id=requirement_id).order_by(
        QAMessage.round.desc()
    ).first()
    return (last.round + 1) if last else 1
