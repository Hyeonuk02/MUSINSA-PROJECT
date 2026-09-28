package com.pm.payment.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;

import com.pm.payment.entity.Refund;

@Repository
public interface RefundRepository extends JpaRepository<Refund, Long> {

}
