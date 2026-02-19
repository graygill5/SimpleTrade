import React from "react";
export default function Card({ title, children, right }) {
  return (
    <div className="card">
      <div style={{display:"flex", justifyContent:"space-between", alignItems:"center"}}>
        <h3 style={{margin:"0 0 12px"}}>{title}</h3>
        {right}
      </div>
      {children}
    </div>
  );
}

