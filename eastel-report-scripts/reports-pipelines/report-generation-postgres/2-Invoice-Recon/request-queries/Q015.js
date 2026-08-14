/*
Copy-paste sample for July 2026:

db.smsc_cdrs.aggregate([
  {
    $match: {
      delivery_date: { $gte: ISODate("2026-07-01T00:00:00Z"), $lt: ISODate("2026-08-01T00:00:00Z") },
      message_type: "message",
      origination_type: "SMPP",
      message_delivery_status: { $in: ["success", "success_esme"] },
      $or: [
        { addr_src_digits: { $regex: "^2" } },
        { addr_src_digits: "601170337777" },
        { addr_src_digits: { $regex: "^6" } }
      ]
    }
  },
  {
    $addFields: {
      charge_type: {
        $switch: {
          branches: [
            { case: { $or: [{ $regexMatch: { input: { $ifNull: ["$addr_src_digits", ""] }, regex: "^2" } }, { $eq: ["$addr_src_digits", "601170337777"] }] }, then: "Non-Profit A2P SMS MT Bundled" },
            { case: { $and: [{ $regexMatch: { input: { $ifNull: ["$addr_src_digits", ""] }, regex: "^6" } }, { $ne: ["$addr_src_digits", "601170337777"] }] }, then: "Commercial A2P SMS MT" }
          ],
          default: null
        }
      },
      sms_type: {
        $switch: {
          branches: [
            { case: { $or: [{ $regexMatch: { input: { $ifNull: ["$addr_src_digits", ""] }, regex: "^2" } }, { $eq: ["$addr_src_digits", "601170337777"] }] }, then: "Non Profit A2P (22200,22288,22200EASTEL,601170337777)" },
            { case: { $and: [{ $regexMatch: { input: { $ifNull: ["$addr_src_digits", ""] }, regex: "^6" } }, { $ne: ["$addr_src_digits", "601170337777"] }] }, then: "Commercial A2P" }
          ],
          default: null
        }
      }
    }
  },
  { $match: { charge_type: { $ne: null } } },
  { $group: { _id: { charge_type: "$charge_type", sms_type: "$sms_type" }, sms_count: { $sum: 1 } } },
  { $project: { _id: 0, service_type: { $literal: "SMS" }, charge_type: "$_id.charge_type", sms_type: "$_id.sms_type", sms_count: 1 } }
]);
*/

db.{{smsc_cdr}}.aggregate([
  {
    $match: {
      delivery_date: { $gte: ISODate("{{start_date}}"), $lt: ISODate("{{end_date}}") },
      message_type: "message",
      origination_type: "SMPP",
      message_delivery_status: { $in: ["success", "success_esme"] },
      $or: [
        { addr_src_digits: { $regex: "^2" } },
        { addr_src_digits: "601170337777" },
        { addr_src_digits: { $regex: "^6" } }
      ]
    }
  }
]);
