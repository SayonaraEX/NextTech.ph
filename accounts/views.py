# accounts/views.py
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from products.models import Product
from .models import Cart, CartItem, Order, OrderItem
from django.db import transaction

def register_user(request):
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Registration successful. You are now logged in.")
            return redirect('products:home')
        else:
            messages.error(request, "Registration failed. Please correct the errors below.")
    else:
        form = UserCreationForm()
    context = {
        'page_title': 'Register',
        'form': form
    }
    return render(request, 'accounts/register.html', context)

def login_user(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect('products:home')
        else:
            messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    context = {
        'page_title': 'Login',
        'form': form
    }
    return render(request, 'accounts/login.html', context)

# View for user logout
def logout_user(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('products:home')

@login_required
def view_cart(request):
    cart, created = Cart.objects.get_or_create(user=request.user)
    cart_items = cart.cartitem_set.all()

    context = {
        'page_title': 'Your Shopping Cart',
        'cart': cart,
        'cart_items': cart_items,
    }
    return render(request, 'accounts/cart.html', context)

@login_required
def add_to_cart(request, product_id):
    if request.method == 'POST':
        product = get_object_or_404(Product, pk=product_id)
        quantity = int(request.POST.get('quantity', 1))

        if quantity <= 0:
            messages.error(request, "Quantity must be at least 1.")
            return redirect('products:product_detail', pk=product_id)

        if quantity > product.stock_quantity:
            messages.error(request, f"Not enough stock for {product.name}. Available: {product.stock_quantity}")
            return redirect('products:product_detail', pk=product_id)

        cart, created = Cart.objects.get_or_create(user=request.user)

        cart_item, item_created = CartItem.objects.get_or_create(
            cart=cart,
            product=product,
            defaults={'quantity': quantity}
        )

        if not item_created:
            new_quantity = cart_item.quantity + quantity
            if new_quantity > product.stock_quantity:
                messages.error(request, f"Cannot add {quantity} more to cart. Max stock for {product.name}: {product.stock_quantity}.")
                return redirect('products:product_detail', pk=product_id)
            cart_item.quantity = new_quantity
            cart_item.save()
            messages.success(request, f"Updated quantity of {product.name} in your cart. New quantity: {cart_item.quantity}.")
        else:
            messages.success(request, f"Added {product.name} to your cart.")

        return redirect('accounts:view_cart')
    else:
        messages.error(request, "Invalid request method for adding to cart.")
        return redirect('products:product_list')

# View for updating the quantity of a cart item
@login_required
def update_cart_item(request, item_id):
    if request.method == 'POST':
        cart_item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
        try:
            new_quantity = int(request.POST.get('quantity'))
        except (ValueError, TypeError):
            messages.error(request, "Invalid quantity provided.")
            return redirect('accounts:view_cart')

        if new_quantity <= 0:
            cart_item.delete()
            messages.info(request, f"Removed {cart_item.product.name} from your cart.")
        elif new_quantity > cart_item.product.stock_quantity:
            messages.error(request, f"Cannot update quantity to {new_quantity}. Only {cart_item.product.stock_quantity} available for {cart_item.product.name}.")
        else:
            cart_item.quantity = new_quantity
            cart_item.save()
            messages.success(request, f"Updated quantity of {cart_item.product.name} to {new_quantity}.")

        return redirect('accounts:view_cart')
    else:
        messages.error(request, "Invalid request method for updating cart item.")
        return redirect('accounts:view_cart')

# View for removing an item from the cart
@login_required
def remove_from_cart(request, item_id):
    if request.method == 'POST':
        cart_item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
        product_name = cart_item.product.name
        cart_item.delete()
        messages.info(request, f"Removed {product_name} from your cart.")
        return redirect('accounts:view_cart')
    else:
        messages.error(request, "Invalid request method for removing item from cart.")
        return redirect('accounts:view_cart')

# View for handling the checkout process
@login_required
def checkout(request):
    cart = get_object_or_404(Cart, user=request.user)
    cart_items = cart.cartitem_set.all()

    if not cart_items:
        messages.error(request, "Your cart is empty. Please add items before checking out.")
        return redirect('accounts:view_cart')

    if request.method == 'POST':
        shipping_address = request.POST.get('shipping_address')
        if not shipping_address:
            messages.error(request, "Shipping address is required.")
            return render(request, 'accounts/checkout.html', {
                'page_title': 'Checkout',
                'cart': cart,
                'cart_items': cart_items,
                'shipping_address_default': '',
            })

        try:
            with transaction.atomic():
                order = Order.objects.create(
                    user=request.user,
                    total_amount=cart.total_price,
                    shipping_address=shipping_address,
                    status='Pending'
                )

                for item in cart_items:
                    if item.quantity > item.product.stock_quantity:
                        raise ValueError(f"Not enough stock for {item.product.name}. Only {item.product.stock_quantity} available.")

                    OrderItem.objects.create(
                        order=order,
                        product=item.product,
                        quantity=item.quantity,
                        price_at_order=item.product.price
                    )
                    product = item.product
                    product.stock_quantity -= item.quantity
                    product.save()

                cart.cartitem_set.all().delete()

                messages.success(request, f"Your order #{order.id} has been placed successfully!")
                return redirect('products:home')
        except ValueError as e:
            messages.error(request, f"Order placement failed: {e}")
            return redirect('accounts:view_cart')
        except Exception as e:
            messages.error(request, f"An unexpected error occurred during checkout: {e}")
            return redirect('accounts:view_cart')

    else:
        shipping_address_default = ""
        context = {
            'page_title': 'Checkout',
            'cart': cart,
            'cart_items': cart_items,
            'shipping_address_default': shipping_address_default,
        }
        return render(request, 'accounts/checkout.html', context)

@login_required 
def user_profile(request):
    user_orders = Order.objects.filter(user=request.user).order_by('-order_date')
    context = {
        'page_title': 'User Profile & Orders',
        'user_obj': request.user, 
        'orders': user_orders,   
    }
    return render(request, 'accounts/user_profile.html', context)
