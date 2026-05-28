import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const api = async (path, options) => {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || "请求失败");
  return data;
};

function App() {
  const [categories, setCategories] = useState([]);
  const [products, setProducts] = useState([]);
  const [coupons, setCoupons] = useState([]);
  const [daily, setDaily] = useState([]);
  const [orders, setOrders] = useState([]);
  const [cart, setCart] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [keyword, setKeyword] = useState("");
  const [couponCode, setCouponCode] = useState("");
  const [message, setMessage] = useState("");
  const [user, setUser] = useState(() => JSON.parse(localStorage.getItem("eshop_user") || "null"));
  const [loginForm, setLoginForm] = useState({ email: "user1@example.edu", password: "demo123456" });

  const cartTotal = useMemo(
    () => cart.reduce((sum, item) => sum + item.price * item.quantity, 0),
    [cart]
  );

  const loadCatalog = async () => {
    const query = new URLSearchParams();
    if (selectedCategory) query.set("categoryId", selectedCategory);
    if (keyword) query.set("q", keyword);
    const [categoryRows, productRows, couponRows, dailyRows] = await Promise.all([
      api("/categories"),
      api(`/products?${query.toString()}`),
      api("/coupons"),
      api("/analytics/daily")
    ]);
    setCategories(categoryRows);
    setProducts(productRows);
    setCoupons(couponRows);
    setDaily(dailyRows.slice(0, 8));
  };

  const loadOrders = async (nextUser = user) => {
    if (!nextUser) return setOrders([]);
    const rows = await api(`/orders?userId=${nextUser.userId}`);
    setOrders(rows);
  };

  useEffect(() => {
    loadCatalog().catch((error) => setMessage(error.message));
  }, [selectedCategory, keyword]);

  useEffect(() => {
    loadOrders().catch((error) => setMessage(error.message));
  }, [user?.userId]);

  const login = async (event) => {
    event.preventDefault();
    try {
      const nextUser = await api("/auth/login", {
        method: "POST",
        body: JSON.stringify(loginForm)
      });
      localStorage.setItem("eshop_user", JSON.stringify(nextUser));
      setUser(nextUser);
      setMessage(`欢迎回来，${nextUser.name}`);
      await loadOrders(nextUser);
    } catch (error) {
      setMessage(error.message);
    }
  };

  const addToCart = (product) => {
    setCart((items) => {
      const existing = items.find((item) => item.skuId === product.skuId);
      if (existing) {
        return items.map((item) => item.skuId === product.skuId ? { ...item, quantity: item.quantity + 1 } : item);
      }
      return [...items, { ...product, quantity: 1 }];
    });
    setMessage(`${product.skuName} 已加入购物车`);
  };

  const updateQuantity = (skuId, quantity) => {
    setCart((items) => items
      .map((item) => item.skuId === skuId ? { ...item, quantity: Math.max(1, quantity) } : item)
      .filter((item) => item.quantity > 0));
  };

  const checkout = async () => {
    if (!user) return setMessage("请先登录演示用户");
    if (cart.length === 0) return setMessage("购物车为空");

    try {
      const order = await api("/checkout", {
        method: "POST",
        body: JSON.stringify({
          userId: user.userId,
          couponCode: couponCode || undefined,
          channel: "web_demo",
          items: cart.map((item) => ({ skuId: item.skuId, quantity: item.quantity }))
        })
      });
      setCart([]);
      setCouponCode("");
      setMessage(`下单成功：${order.orderNo}，实付 ¥${order.paidAmount}`);
      await Promise.all([loadCatalog(), loadOrders()]);
    } catch (error) {
      setMessage(error.message);
    }
  };

  return (
    <div className="shell">
      <header className="hero">
        <div>
          <p className="eyebrow">数据挖掘与商业决策课程样例</p>
          <h1>Course eShop 在线商城</h1>
          <p>已内置公开教学样例商品、免版权占位图片和可复现经营数据，学生可基于同一数据源做挖掘与运营支持。</p>
        </div>
        <form className="login-card" onSubmit={login}>
          <strong>{user ? `当前用户：${user.name}` : "演示登录"}</strong>
          <input value={loginForm.email} onChange={(e) => setLoginForm({ ...loginForm, email: e.target.value })} placeholder="邮箱" />
          <input value={loginForm.password} onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })} placeholder="密码" type="password" />
          <button>登录</button>
        </form>
      </header>

      {message && <div className="toast">{message}</div>}

      <section className="toolbar">
        <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)}>
          <option value="">全部类目</option>
          {categories.map((category) => <option key={category.categoryId} value={category.categoryId}>{category.name}</option>)}
        </select>
        <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="搜索商品、品牌或类目" />
      </section>

      <main className="layout">
        <section>
          <h2>商品列表</h2>
          <div className="grid">
            {products.map((product) => (
              <article className="product-card" key={product.skuId}>
                <img src={product.imageUrl} alt={product.skuName} />
                <div className="product-body">
                  <span>{product.categoryName} / {product.brand}</span>
                  <h3>{product.skuName}</h3>
                  <p>{product.description}</p>
                  <div className="price-row">
                    <strong>¥{product.price}</strong>
                    <small>库存 {product.stock}</small>
                  </div>
                  <button onClick={() => addToCart(product)}>加入购物车</button>
                </div>
              </article>
            ))}
          </div>
        </section>

        <aside className="side">
          <section className="panel">
            <h2>购物车</h2>
            {cart.length === 0 ? <p className="muted">暂未选择商品</p> : cart.map((item) => (
              <div className="cart-line" key={item.skuId}>
                <span>{item.skuName}</span>
                <input type="number" min="1" value={item.quantity} onChange={(e) => updateQuantity(item.skuId, Number(e.target.value))} />
              </div>
            ))}
            <label>
              优惠码
              <select value={couponCode} onChange={(e) => setCouponCode(e.target.value)}>
                <option value="">不使用</option>
                {coupons.map((coupon) => <option key={coupon.couponId} value={coupon.code}>{coupon.code}：满{coupon.threshold}减{coupon.discount}</option>)}
              </select>
            </label>
            <div className="total">商品小计 ¥{cartTotal.toFixed(2)}</div>
            <button className="primary" onClick={checkout}>模拟支付并下单</button>
          </section>

          <section className="panel">
            <h2>我的订单</h2>
            {orders.slice(0, 4).map((order) => (
              <div className="order" key={order.orderId}>
                <strong>{order.orderNo}</strong>
                <span>{order.status} / ¥{order.paidAmount}</span>
              </div>
            ))}
            {orders.length === 0 && <p className="muted">登录后查看订单</p>}
          </section>

          <section className="panel">
            <h2>经营数据快照</h2>
            {daily.map((row) => (
              <div className="metric" key={`${row.date}-${row.channel}`}>
                <span>{row.date} · {row.channel}</span>
                <strong>GMV ¥{row.gmv}</strong>
              </div>
            ))}
          </section>
        </aside>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
