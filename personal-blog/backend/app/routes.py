from typing import Any

from flask import Blueprint, current_app, request
from sqlalchemy import desc

from .models import Category, Comment, Post, Tag, User, db

api_bp = Blueprint('api', __name__)


def post_to_dict(post: Post, with_content: bool = False) -> dict[str, Any]:
    data = {
        'id': post.id,
        'title': post.title,
        'summary': post.summary,
        'is_published': post.is_published,
        'category': post.category.name if post.category else None,
        'category_id': post.category_id,
        'tags': [tag.name for tag in post.tags],
        'created_at': post.created_at.isoformat(),
        'updated_at': post.updated_at.isoformat(),
        'comment_count': len(post.comments),
    }
    if with_content:
        data['content'] = post.content
    return data


def ensure_admin() -> bool:
    token = request.headers.get('X-Admin-Token')
    return token and token == current_app.config.get('ADMIN_TOKEN')


@api_bp.post('/auth/login')
def login():
    payload = request.get_json(silent=True) or {}
    username = payload.get('username', '').strip()
    password = payload.get('password', '')

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return {'message': '用户名或密码错误'}, 401

    token = f"admin-{user.id}-{user.updated_at.timestamp()}"
    current_app.config['ADMIN_TOKEN'] = token
    return {'token': token, 'username': user.username}


@api_bp.get('/bootstrap')
def bootstrap_data():
    categories = Category.query.order_by(Category.name.asc()).all()
    tags = Tag.query.order_by(Tag.name.asc()).all()
    latest_posts = Post.query.filter_by(is_published=True).order_by(desc(Post.created_at)).limit(8).all()

    return {
        'categories': [{'id': c.id, 'name': c.name} for c in categories],
        'tags': [{'id': t.id, 'name': t.name} for t in tags],
        'latest_posts': [post_to_dict(post) for post in latest_posts],
    }


@api_bp.get('/posts')
def list_posts():
    category_id = request.args.get('category_id', type=int)
    tag_name = request.args.get('tag')
    keyword = (request.args.get('keyword') or '').strip()

    query = Post.query.filter_by(is_published=True)
    if category_id:
        query = query.filter_by(category_id=category_id)
    if tag_name:
        query = query.join(Post.tags).filter(Tag.name == tag_name)
    if keyword:
        pattern = f'%{keyword}%'
        query = query.filter(Post.title.like(pattern) | Post.summary.like(pattern) | Post.content.like(pattern))

    posts = query.order_by(desc(Post.created_at)).all()
    return {'items': [post_to_dict(post) for post in posts]}


@api_bp.get('/posts/<int:post_id>')
def get_post(post_id: int):
    post = Post.query.get_or_404(post_id)
    if not post.is_published:
        return {'message': '文章未发布'}, 404

    comments = (
        Comment.query.filter_by(post_id=post.id)
        .order_by(Comment.created_at.desc())
        .all()
    )
    return {
        'post': post_to_dict(post, with_content=True),
        'comments': [
            {
                'id': c.id,
                'author': c.author,
                'content': c.content,
                'created_at': c.created_at.isoformat(),
            }
            for c in comments
        ],
    }


@api_bp.post('/posts/<int:post_id>/comments')
def add_comment(post_id: int):
    post = Post.query.get_or_404(post_id)
    if not post.is_published:
        return {'message': '文章未发布'}, 400

    payload = request.get_json(silent=True) or {}
    author = payload.get('author', '').strip()
    content = payload.get('content', '').strip()
    if not author or not content:
        return {'message': '请填写昵称和评论内容'}, 400

    comment = Comment(author=author[:80], content=content, post_id=post.id)
    db.session.add(comment)
    db.session.commit()
    return {'message': '评论成功'}


@api_bp.post('/admin/seed')
def seed_admin():
    if User.query.filter_by(username=current_app.config['ADMIN_USERNAME']).first():
        return {'message': '初始化已完成'}

    admin = User(username=current_app.config['ADMIN_USERNAME'], is_admin=True)
    admin.set_password(current_app.config['ADMIN_PASSWORD'])
    db.session.add(admin)

    default_category = Category(name='默认分类')
    db.session.add(default_category)

    for name in ['技术', '生活', '随笔']:
        db.session.add(Tag(name=name))

    sample_post = Post(
        title='欢迎来到我的博客',
        summary='这是第一篇示例文章，你可以在管理后台中编辑或删除它。',
        content='## Hello Blog\n\n这是一个基于 Vue + Element UI + Flask 的个人博客示例。',
        category=default_category,
        is_published=True,
    )
    db.session.add(sample_post)
    db.session.commit()
    return {'message': '初始化成功'}


@api_bp.get('/admin/posts')
def admin_posts():
    if not ensure_admin():
        return {'message': '未授权'}, 401

    posts = Post.query.order_by(desc(Post.created_at)).all()
    return {'items': [post_to_dict(post, with_content=True) for post in posts]}


@api_bp.post('/admin/posts')
def create_post():
    if not ensure_admin():
        return {'message': '未授权'}, 401

    payload = request.get_json(silent=True) or {}
    title = payload.get('title', '').strip()
    content = payload.get('content', '').strip()
    summary = payload.get('summary', '').strip()
    category_id = payload.get('category_id')
    tag_names = payload.get('tags', [])
    is_published = bool(payload.get('is_published', True))

    if not title or not content:
        return {'message': '标题和内容必填'}, 400

    post = Post(title=title, content=content, summary=summary, is_published=is_published, category_id=category_id)
    post.tags = _upsert_tags(tag_names)
    db.session.add(post)
    db.session.commit()
    return {'message': '创建成功', 'id': post.id}


@api_bp.put('/admin/posts/<int:post_id>')
def update_post(post_id: int):
    if not ensure_admin():
        return {'message': '未授权'}, 401

    post = Post.query.get_or_404(post_id)
    payload = request.get_json(silent=True) or {}
    post.title = payload.get('title', post.title)
    post.summary = payload.get('summary', post.summary)
    post.content = payload.get('content', post.content)
    post.is_published = bool(payload.get('is_published', post.is_published))
    post.category_id = payload.get('category_id', post.category_id)
    if 'tags' in payload:
        post.tags = _upsert_tags(payload.get('tags', []))

    db.session.commit()
    return {'message': '更新成功'}


@api_bp.delete('/admin/posts/<int:post_id>')
def delete_post(post_id: int):
    if not ensure_admin():
        return {'message': '未授权'}, 401

    post = Post.query.get_or_404(post_id)
    db.session.delete(post)
    db.session.commit()
    return {'message': '删除成功'}


def _upsert_tags(tag_names: list[str]) -> list[Tag]:
    tags = []
    for raw_name in tag_names:
        name = (raw_name or '').strip()
        if not name:
            continue
        tag = Tag.query.filter_by(name=name).first()
        if not tag:
            tag = Tag(name=name)
            db.session.add(tag)
        tags.append(tag)
    return tags
